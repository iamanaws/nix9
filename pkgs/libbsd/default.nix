{ stdenv, src }:
stdenv.mkDerivation {
  name = "libbsd";
  inherit src;
  sourceRoot = "source/sys/src/ape/lib/bsd";
  buildPhase = ''
    mkdir -p $out/lib/ape
    ${
      if stdenv.buildPlatform.system == stdenv.hostPlatform.system then
        ''
          bind `{pwd}^/../.. /sys/src/ape
          bind -c $out/lib/ape /amd64/lib/ape
        ''
      else
        ''
          rm -rf $NIX9_ROOT/amd64/lib/ape
          ln -s $out/lib/ape $NIX9_ROOT/amd64/lib/ape
        ''
    }
    mk install
  '';
  installPhase = "test -s $out/lib/ape/libbsd.a";
}
