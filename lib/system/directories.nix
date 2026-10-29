{
  lib,
  mkDerivation,
  directories,
  mounts,
}:
let
  paths = builtins.attrNames directories;
  runtimeFile = (import ./modules/types.nix { inherit lib; }).runtimeFile;
  below = parent: child: parent == child || lib.hasPrefix (parent + "/") child;
  protected = [
    "/bin"
    "/dev"
    "/env"
    "/fd"
    "/mnt"
    "/n"
    "/net"
    "/net.alt"
    "/proc"
    "/srv"
    "/usr/local/nix"
    "/usr/local/pkg"
    "/cfg/nix9"
    "/sys/lib/tls/webfs"
  ];
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  optional = value: if value == null then "-" else value;
  arguments = lib.concatMapStringsSep " " (
    path:
    let
      settings = directories.${path};
    in
    lib.concatMapStringsSep " " quote [
      path
      settings.mode
      (optional settings.owner)
      (optional settings.group)
    ]
  ) paths;
  tool = mkDerivation {
    name = "nix9-directories";
    buildCommand = ''
      mkdir -p $out/bin
      cp ${./directories.c} directories.c
      6c -o directories.6 directories.c
      6l -o $out/bin/nix9-directories directories.6
    '';
  };
in
if !builtins.all runtimeFile.check paths then
  throw "mkSystem: directories must use canonical absolute runtime paths outside the Nix store"
else if
  builtins.any (
    path: builtins.any (reserved: below reserved path || below path reserved) protected
  ) paths
then
  throw "mkSystem: directories must not cover native namespace paths, the Nix runtime or generated system mounts"
else if
  builtins.any (
    path: builtins.any (mount: below mount.mountPoint path) (builtins.attrValues mounts)
  ) paths
then
  throw "mkSystem: directories must not modify session mount destinations or their contents"
else if paths == [ ] then
  null
else
  {
    inherit paths;
    script = ''
      #!/bin/rc -e
      rfork e
      fn checkSessionMounts {
        while(! ~ $#* 0) {
          if(~ $#* 1 2 3) exit 'invalid inherited session mount state'
          for(directory in (${lib.concatMapStringsSep " " quote paths})) {
            if(~ $directory $2 $2^/*) {
              echo 'nix9: directory is inside a retained session mount:' $directory >[1=2]
              exit 'directory overlaps session mount'
            }
          }
          shift 4
        }
      }
      checkSessionMounts $nix9NamespaceMounts
      exec ${tool}/bin/nix9-directories $* ${arguments}
    '';
  }
