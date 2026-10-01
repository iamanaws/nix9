{ pkgs }:
{ name, packages }:
let
  inherit (pkgs) lib;
  guestPrefix = "/usr/local/env/${name}";
  prefixes = map (package: package.guestPrefix) packages;
in
assert builtins.match "[a-zA-Z0-9][a-zA-Z0-9._+-]*" name != null;
assert packages != [ ];
assert lib.length (lib.unique prefixes) == lib.length prefixes;
pkgs.runCommand "${name}-environment.tar" { passthru = { inherit guestPrefix; }; } ''
  mkdir -p root${guestPrefix}
  declare -A commands
  ${lib.concatMapStringsSep "\n" (package: ''
    tar -xf ${package} -C root
    for command in root${package.guestPrefix}/bin/*; do
      [ -e "$command" ] || continue
      commandName="''${command##*/}"
      if [ -n "''${commands[$commandName]:-}" ]; then
        echo "Conflicting command $commandName: ''${commands[$commandName]} and ${package.guestPrefix}" >&2
        exit 1
      fi
      commands[$commandName]=${package.guestPrefix}
    done
  '') packages}
  cat > root${guestPrefix}/activate <<'EOF'
  ${lib.concatMapStringsSep "\n" (package: ". ${package.guestPrefix}/activate") (
    lib.reverseList packages
  )}
  EOF
  tar --format=ustar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -cf "$out" -C root usr
''
