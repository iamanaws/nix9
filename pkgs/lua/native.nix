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
      cp /sys/include/ape/$header .
    }
    objtype=amd64
    $tools/bin/pcc -c lua.c
    $tools/bin/pcc -o lua lua.6 -llua
  '';
  doCheck = true;
  checkPhase = ''
    ./lua -e 'assert(6 * 7 == 42)'
  '';
  installPhase = ''
    $tools/bin/mkdir -p $out/bin
    $tools/bin/cp lua $out/bin/lua
  '';
}
