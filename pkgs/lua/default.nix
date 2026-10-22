{
  mkDerivation,
  fetchurl,
  upstream,
  liblua,
}:
mkDerivation {
  pname = "lua";
  version = upstream.version;
  src = fetchurl upstream.src;
  buildInputs = [ liblua ];
  sourceRoot = "lua-${upstream.version}/src";
  buildPhase = ''
    for(header in lua.h luaconf.h lauxlib.h lualib.h lprefix.h ape-config.h) {
      cp ${liblua}/include/ape/$header .
    }
    objtype=amd64
    pcc -c lua.c
    pcc -o lua lua.6 -llua
  '';
  doCheck = true;
  checkPhase = ''
    ./lua -e 'assert(6 * 7 == 42)'
  '';
  installPhase = ''
    mkdir -p $out/bin $out/share/lua/5.4 $out/share/doc/lua
    cp lua $out/bin/lua
    cp ../doc/readme.html $out/share/doc/lua/
  '';
}
