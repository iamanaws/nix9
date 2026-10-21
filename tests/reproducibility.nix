{ packages }:
let
  pkgs = import packages;
in
pkgs.stdenv.mkDerivation {
  name = "ar-epoch-tests";
  src = builtins.toFile "fixture.c" "int answer(void) { return 42; }\n";
  buildCommand = ''
    mkdir -p $out
    cp $src fixture.c
    6c -o fixture.6 fixture.c
    @{ SOURCE_DATE_EPOCH=0; ar rc $out/zero.a fixture.6 }
    @{ SOURCE_DATE_EPOCH=42; ar rc $out/custom.a fixture.6 }
    @{ rm /env/SOURCE_DATE_EPOCH; ar rc $out/ordinary.a fixture.6 }
  '';
}
