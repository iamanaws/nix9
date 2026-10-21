{
  mkDerivation,
  fetchurl,
  upstream,
  config,
}:
mkDerivation {
  pname = "liblua";
  version = upstream.version;
  src = fetchurl upstream.src;
  inherit config;
  sourceRoot = "lua-${upstream.version}/src";
  buildPhase = ''
    $tools/bin/sed 's|@guestPrefix@|'$out'|g' $config > ape-config.h
    for(header in lprefix.h luaconf.h) {
      $tools/bin/echo '#include "ape-config.h"' > header.tmp
      $tools/bin/cat $header >> header.tmp
      $tools/bin/cp header.tmp $header
    }
    objtype=amd64
    for(source in *.c) {
      if(! ~ $source lua.c luac.c) $tools/bin/pcc -c $source
    }
  '';
  installPhase = ''
    $tools/bin/mkdir -p $out/lib/ape $out/include/ape $out/share/lua/5.4 $out/share/doc/lua
    ar rc $out/lib/ape/liblua.a *.6
    for(header in lua.h luaconf.h lauxlib.h lualib.h lprefix.h ape-config.h) {
      $tools/bin/cp $header $out/include/ape/$header
    }
    $tools/bin/cp ../doc/readme.html $out/share/doc/lua/readme.html
  '';
}
