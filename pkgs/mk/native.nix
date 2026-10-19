{
  mkDerivation,
  src,
  libbio,
  libregexp,
}:
mkDerivation {
  name = "mk";
  inherit src;
  buildInputs = [
    libbio
    libregexp
  ];
  doCheck = true;
  checkPhase = "./6.out -n";
}
