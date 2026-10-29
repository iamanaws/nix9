{ runCommand, path }:
runCommand "nix9-module-library" { } ''
  mkdir -p "$out/maintainers"
  cp -rL ${path}/lib "$out/lib"
  cp -L ${path}/COPYING "$out/COPYING"
  cp -L ${path}/maintainers/{maintainer-list,team-list,computed-team-list}.nix "$out/maintainers/"
''
