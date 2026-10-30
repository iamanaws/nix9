{
  lib,
  configuration,
  package,
}:
let
  inherit (configuration)
    enable
    configDevice
    deviceMap
    port
    keyFile
    cachePercent
    autoDump
    dumpHour
    ;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  selected = package.override { inherit autoDump dumpHour; };
  error = message: throw "mkSystem: services.cwfs.${message}";
in
if !enable then
  if
    configDevice != null
    || deviceMap != { }
    || keyFile != null
    || port != 564
    || cachePercent != 10
    || !autoDump
    || dumpHour != 5
  then
    error "settings require enable"
  else
    null
else if configDevice == null then
  error "configDevice must name a provisioned data filesystem"
else if
  !builtins.all (name: builtins.match "w[0-9]+(\\.[0-9]+)*" name != null) (
    builtins.attrNames deviceMap
  )
then
  error "deviceMap keys must be wren names, such as w0"
else
  {
    inherit selected;
    map = lib.concatStringsSep "" (lib.mapAttrsToList (name: path: "${name} ${path}\n") deviceMap);
    settings = ''
      cwfsPackage=${selected}
      cwfsDevice=${quote configDevice}
      cwfsDevices=(${
        lib.concatMapStringsSep " " quote (lib.unique ([ configDevice ] ++ builtins.attrValues deviceMap))
      })
      cwfsKey=${if keyFile == null then "()" else quote keyFile}
      cwfsPort=${toString port}
      cwfsCache=${toString cachePercent}
    '';
  }
