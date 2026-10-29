{
  lib,
  auth,
  cpu,
  authPackage,
  cpuPackage,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  inherit (import ./modules/types.nix { inherit lib; }) userName;
  error = message: throw "mkSystem: ${message}";
in
if cpu.enable && cpu.allowedUsers == [ ] then
  error "services.cpu.allowedUsers must name at least one user"
else if !cpu.enable && (cpu.allowedUsers != [ ] || cpu.keyFile != null || cpu.keyPattern != "") then
  error "CPU settings require services.cpu.enable"
else if
  builtins.match ".*[\r\n].*" cpu.keyPattern != null || builtins.match ".*!.*" cpu.keyPattern != null
then
  error "services.cpu.keyPattern must contain only public attributes on one line"
else if !builtins.all userName.check (builtins.attrNames auth.speaksFor) then
  error "services.auth.speaksFor contains an invalid identity"
else if !auth.enable && (auth.keyDatabase != "/adm/keys" || auth.speaksFor != { }) then
  error "authentication settings require services.auth.enable"
else if !auth.enable && !cpu.enable then
  null
else
  {
    inherit auth cpu;
    packages = (lib.optional auth.enable authPackage) ++ (lib.optional cpu.enable cpuPackage);
    settings = ''
      nix9AuthEnabled=${if auth.enable then "1" else "0"}
      nix9CpuEnabled=${if cpu.enable then "1" else "0"}
      nix9AuthDatabase=${quote auth.keyDatabase}
      nix9CpuKeys=${if cpu.keyFile == null then "()" else quote cpu.keyFile}
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
