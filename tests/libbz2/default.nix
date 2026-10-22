{ mkDerivation, libbz2 }:
mkDerivation {
  name = "libbz2-consumer";
  src = ./main.c;
  buildInputs = [ libbz2 ];
  buildCommand = ''
    pcc -c -o main.6 $src
    mkdir -p $out/bin
    pcc -o $out/bin/bz2-test main.6 -lbz2
    cp main.6 $out/main.6
  '';
}
