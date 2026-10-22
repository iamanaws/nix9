{
  mkDerivation,
  libap,
  libbsd,
}:
mkDerivation {
  name = "ape-cross";
  src = ./main.c;
  buildInputs = [
    libap
    libbsd
  ];
  buildCommand = ''
    pcc -c -o main.6 $src
    mkdir -p $out/bin
    pcc -o $out/bin/ape-tests main.6
  '';
}
