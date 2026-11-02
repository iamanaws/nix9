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
    users
    directories
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
    || users != { }
    || directories != { }
  then
    error "settings require enable"
  else
    null
else if configDevice == null then
  error "configDevice must name a provisioned data filesystem"
else if
  !builtins.all (
    name:
    builtins.stringLength name < 28
    && builtins.match "[a-zA-Z0-9][a-zA-Z0-9_.]*" name != null
    && name != "none"
    && name != "adm"
  ) (builtins.attrNames users)
then
  error "users must use native names shorter than 28 bytes, excluding adm and none"
else if
  builtins.length (lib.unique (map (user: user.id) (builtins.attrValues users)))
  != builtins.length (builtins.attrNames users)
then
  error "users must have distinct on-disk IDs"
else if
  builtins.any (user: builtins.length user.members != builtins.length (lib.unique user.members)) (
    builtins.attrValues users
  )
then
  error "users must not repeat group members"
else if
  !builtins.all (
    path:
    (import ./modules/types.nix { inherit lib; }).runtimeFile.check path
    && path != "/adm"
    && !lib.hasPrefix "/adm/" path
  ) (builtins.attrNames directories)
then
  error "directories must use canonical absolute paths outside /adm and the Nix store"
else if
  builtins.any (directory: directory.owner == null || directory.group == null) (
    builtins.attrValues directories
  )
then
  error "directories require explicit native owners and groups"
else if
  !builtins.all (name: builtins.match "w[0-9]+(\\.[0-9]+)*" name != null) (
    builtins.attrNames deviceMap
  )
then
  error "deviceMap keys must be wren names, such as w0"
else
  {
    inherit selected;
    userTable = lib.concatStrings (
      lib.mapAttrsToList (
        name: user:
        "${toString user.id}:${name}:${
          if user.leader == null then "" else user.leader
        }:${lib.concatStringsSep "," user.members}\n"
      ) users
    );
    directoryTable = lib.concatStrings (
      lib.mapAttrsToList (
        path: directory: "${path} ${directory.owner} ${directory.group} ${directory.mode}\n"
      ) directories
    );
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
      cwfsManagedUsers=${if users != { } || directories != { } then "1" else "0"}
    '';
  }
