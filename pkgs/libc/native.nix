{ stdenv, src }:
stdenv.mkDerivation {
  name = "libc";
  inherit src;
  buildPhase = ''
    mkdir -p $out/lib
    bind -c $out/lib /amd64/lib
    # Use the Unicode tables shipped with the pinned source tree.
    mk 'UCD=' install
  '';
  installPhase = "test -s $out/lib/libc.a";
  meta.description = "Plan 9 C library";
}
