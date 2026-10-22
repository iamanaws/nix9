{ stdenv, src }:
stdenv.mkDerivation {
  name = "libc";
  inherit src;
  buildPhase = ''
    mkdir -p $out/lib
    ${
      if stdenv.buildPlatform.system == stdenv.hostPlatform.system then
        ''
          bind -c $out/lib /amd64/lib
        ''
      else
        ''
          rm -rf $NIX9_ROOT/amd64/lib
          ln -s $out/lib $NIX9_ROOT/amd64/lib
        ''
    }
    # Use the Unicode tables shipped with the pinned source tree.
    mk 'UCD=' install
  '';
  installPhase = "test -s $out/lib/libc.a";
  meta.description = "Plan 9 C library";
}
