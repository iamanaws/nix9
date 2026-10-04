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
    rfork n
    $tools/bin/bind $tools/bin /bin
    $tools/bin/bind $tools/sys/include /sys/include
    $tools/bin/bind $tools/amd64/include /amd64/include
    $tools/bin/bind $tools/amd64/lib /amd64/lib
    objtype=amd64
    $tools/bin/mkdir -p $out/bin
    $tools/bin/pcc -c lua.c
    $tools/bin/pcc -o $out/bin/lua lua.6 $liblua/lib/liblua.a
  '';
}
