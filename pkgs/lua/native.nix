{
  mkDerivation,
  fetchurl,
  upstream,
  config,
}:
mkDerivation {
  name = "lua-${upstream.version}";
  src = fetchurl upstream.src;
  inherit config;
  buildCommand = ''
    $tools/bin/gunzip -c $src > source.tar
    $tools/bin/tar xf source.tar
    cd lua-${upstream.version}/src
    $tools/bin/sed 's|@guestPrefix@|'$out'|g' $config > ape-config.h
    $tools/bin/echo '#include "ape-config.h"' > prefix.h
    $tools/bin/cat lprefix.h >> prefix.h
    $tools/bin/cp prefix.h lprefix.h
    rfork n
    $tools/bin/bind $tools/bin /bin
    $tools/bin/bind $tools/sys/include /sys/include
    $tools/bin/bind $tools/amd64/include /amd64/include
    $tools/bin/bind $tools/amd64/lib /amd64/lib
    objtype=amd64
    for(source in *.c) {
      if(! ~ $source luac.c) $tools/bin/pcc -c $source
    }
    $tools/bin/mkdir -p $out/bin $out/share/lua/5.4 $out/share/doc/lua
    $tools/bin/pcc -o $out/bin/lua *.6
    $tools/bin/cp ../doc/readme.html $out/share/doc/lua/readme.html
  '';
}
