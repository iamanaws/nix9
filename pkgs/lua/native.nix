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
  inherit liblua;
  sourceRoot = "lua-${upstream.version}/src";
  buildPhase = ''
    $tools/bin/cp $liblua/include/*.h .
    objtype=amd64
    $tools/bin/pcc -c lua.c
    $tools/bin/pcc -o lua lua.6 $liblua/lib/liblua.a
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
