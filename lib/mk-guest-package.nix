{ pkgs }:
{ name, package }:
let
  guestPrefix = "/usr/local/pkg/${name}";
in
assert builtins.match "[a-zA-Z0-9][a-zA-Z0-9._+-]*" name != null;
assert package.guestPrefix or guestPrefix == guestPrefix;
pkgs.runCommand "${name}-package.tar" { passthru = { inherit guestPrefix; }; } ''
  mkdir -p root${guestPrefix}
  cp -r ${package}/. root${guestPrefix}/
  chmod -R u+w root
  cat > root${guestPrefix}/activate <<'EOF'
  path=(${guestPrefix}/bin $path)
  if(~ $#PATH 0) PATH=/bin
  PATH=${guestPrefix}/bin^:^$PATH
  status='''
  EOF
  tar --format=ustar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -cf "$out" -C root usr
''
