{
  mkDerivation,
  fetchurl,
  upstream,
  liblua,
}:
mkDerivation {
  name = "lua-${upstream.version}";
  src = fetchurl upstream.src;
  inherit liblua;
  buildCommand = ''
    $tools/bin/gunzip -c $src > source.tar
    $tools/bin/tar xf source.tar
    cd lua-${upstream.version}/src
    $tools/bin/cp $liblua/include/*.h .
    objtype=amd64
    $tools/bin/mkdir -p $out/bin
    $tools/bin/pcc -c lua.c
    $tools/bin/pcc -o $out/bin/lua lua.6 $liblua/lib/liblua.a
  '';
}
