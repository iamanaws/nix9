{
  lib,
  binds,
  mounts,
  directories,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  below = parent: child: parent == child || lib.hasPrefix (parent + "/") child;
  overlaps = a: b: below a b || below b a;
  targets = lib.unique (map (binding: binding.target) binds);
  protected = [
    "/bin"
    "/dev"
    "/env"
    "/fd"
    "/mnt"
    "/net"
    "/net.alt"
    "/proc"
    "/srv"
    "/usr/local/nix"
    "/usr/local/pkg"
    "/cfg/nix9"
    "/sys/lib/tls/webfs"
  ];
  error = message: throw "mkSystem: namespace.binds ${message}";
in
if builtins.any (target: builtins.any (overlaps target) protected) targets then
  error "must not cover native namespace paths, the Nix runtime or generated system mounts"
else if builtins.any (binding: lib.hasPrefix "/mnt/nix9-" binding.source) binds then
  error "must not use internal namespace anchors as sources"
else if builtins.any (binding: overlaps binding.source binding.target) binds then
  error "sources and their destinations must not contain one another"
else if
  builtins.any (
    target: builtins.any (other: target != other && overlaps target other) targets
  ) targets
then
  error "destinations must not nest; use repeated destinations for union directories"
else if
  builtins.any (
    target: builtins.any (mount: overlaps target mount.mountPoint) (builtins.attrValues mounts)
  ) targets
then
  error "destinations must not overlap session mount points"
else if
  builtins.any (path: builtins.any (target: path != target && below target path) targets) (
    builtins.attrNames directories
  )
then
  error "must not hide declared directory contents; declare the destination itself instead"
else
  {
    count = 8 * builtins.length binds;
    arguments = lib.concatMapStringsSep " " (
      binding:
      lib.concatMapStringsSep " " quote [
        binding.source
        binding.target
        binding.mode
        (if binding.create then "1" else "0")
        (if binding.required then "1" else "0")
      ]
    ) binds;
    mountPoints = map (mount: mount.mountPoint) (builtins.attrValues mounts);
    planned = builtins.attrNames directories;
  }
