{ runCommand, lua }:
runCommand "lua-${lua.version}-package.tar" { } ''
  mkdir -p root${lua.guestPrefix}
  cp -r ${lua}/. root${lua.guestPrefix}/
  chmod -R u+w root
  mkdir -p root${lua.guestPrefix}/share/lua/5.4
  tar --format=ustar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -cf "$out" -C root usr
''
