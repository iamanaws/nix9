{
  mkDerivation,
  fetchurl,
  upstream,
  config,
  libap,
  libbsd,
  runtimePrefix ? null,
}:
mkDerivation {
  pname = "liblua";
  version = upstream.version;
  src = fetchurl upstream.src;
  inherit config;
  propagatedBuildInputs = [
    libap
    libbsd
  ];
  sourceRoot = "lua-${upstream.version}/src";
  buildPhase = ''
    sed 's|@guestPrefix@|'${
      if runtimePrefix == null then "$out" else runtimePrefix
    }'|g' $config > ape-config.h
    for(header in lprefix.h luaconf.h) {
      echo '#include "ape-config.h"' > header.tmp
      cat $header >> header.tmp
      cp header.tmp $header
    }
    objtype=amd64
    for(source in *.c) {
      if(! ~ $source lua.c luac.c) pcc -c $source
    }
  '';
  installPhase = ''
    mkdir -p $out/lib/ape $out/include/ape $out/share/lua/5.4 $out/share/doc/lua
    ar rc $out/lib/ape/liblua.a *.6
    for(header in lua.h luaconf.h lauxlib.h lualib.h lprefix.h ape-config.h) {
      cp $header $out/include/ape/$header
    }
    cp ../doc/readme.html $out/share/doc/lua/readme.html
  '';
}
