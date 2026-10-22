{
  runCommand,
  fetchurl,
  upstream,
  runtimePrefix,
}:
runCommand "lua-${upstream.version}-ape.tar.gz" { } ''
  tar -xzf ${fetchurl upstream.src}
  cp ${./ape-config.h} lua-${upstream.version}/src/ape-config.h
  substituteInPlace lua-${upstream.version}/src/ape-config.h \
    --replace-fail '@guestPrefix@' '${runtimePrefix}'
  for header in lprefix.h luaconf.h; do
    sed -i '1i#include "ape-config.h"' lua-${upstream.version}/src/$header
  done
  tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
    -czf "$out" lua-${upstream.version}
''
