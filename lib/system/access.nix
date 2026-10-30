{
  lib,
  auth,
  cpu,
  exports,
  cronKeyFile ? null,
  cwfsEnabled ? false,
  cwfsKeyFile ? null,
  authPackage,
  cpuPackage,
  exportfsPackage,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  inherit (import ./modules/types.nix { inherit lib; }) userName;
  error = message: throw "mkSystem: ${message}";
  exportList = builtins.attrValues exports;
  needsFactotum = cpu.enable || exports != { } || cronKeyFile != null || cwfsEnabled;
  keys = lib.unique (
    builtins.filter (key: key != null) (
      (lib.optional cpu.enable cpu.keyFile)
      ++ map (item: item.keyFile) exportList
      ++ [
        cronKeyFile
        cwfsKeyFile
      ]
    )
  );
in
if cpu.enable && cpu.allowedUsers == [ ] then
  error "services.cpu.allowedUsers must name at least one user"
else if !cpu.enable && (cpu.allowedUsers != [ ] || cpu.keyFile != null || cpu.keyPattern != "") then
  error "CPU settings require services.cpu.enable"
else if !builtins.all userName.check (builtins.attrNames auth.speaksFor) then
  error "services.auth.speaksFor contains an invalid identity"
else if !auth.enable && (auth.keyDatabase != "/adm/keys" || auth.speaksFor != { }) then
  error "authentication settings require services.auth.enable"
else if !auth.enable && !needsFactotum then
  null
else
  {
    inherit auth cpu;
    packages =
      (lib.optional auth.enable authPackage)
      ++ (lib.optional needsFactotum cpuPackage)
      ++ (lib.optional (exports != { }) exportfsPackage);
    settings = ''
      nix9AuthEnabled=${if auth.enable then "1" else "0"}
      nix9FactotumRequired=${if needsFactotum then "1" else "0"}
      nix9AuthDatabase=${quote auth.keyDatabase}
      nix9AccessKeys=(${lib.concatMapStringsSep " " quote keys})
      nix9ExportRoots=(${lib.concatMapStringsSep " " (item: quote item.path) exportList})
      nix9AuthPackage=${authPackage}
    '';
    policy = lib.concatStringsSep "" (
      lib.mapAttrsToList (
        host: users: "hostid=${host}" + lib.concatMapStrings (user: " uid=${user}") users + "\n"
      ) auth.speaksFor
    );
    cpuScript = ''
      #!/bin/rc
      if(~ $#* 3) {
        netdir=$3
        remote=$2!`{cat $3/remote}
      }
      fn server {
        if(! ~ $user ${lib.concatMapStringsSep " " quote cpu.allowedUsers}) exit 'CPU access denied'
        ~ $#remote 0 || echo -n $netdir $remote >/proc/$pid/args
        rm -f /env/'fn#server'
        . <{n=`{read} && ! ~ $#n 0 && read -c $n} >[2=1]
      }
      exec ${cpuPackage}/bin/tlssrv -a -k ${quote cpu.keyPattern} /bin/rc -c server
    '';
  }
