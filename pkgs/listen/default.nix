{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
}:
mkDerivation {
  name = "listen";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
  ];
  buildCommand = ''
    cp $src listen.c
    6c -o listen.6 listen.c
    mkdir -p $out/bin/aux
    6l -o $out/bin/aux/listen listen.6
  '';
}
