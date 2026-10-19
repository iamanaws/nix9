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
  buildPhase = "mk";
  doCheck = true;
  checkPhase = "./6.out -n";
  installPhase = ''
    mkdir -p $out/bin
    mk install 'BIN='$out/bin
  '';
}
