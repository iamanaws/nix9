{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
  libip,
  libregexp,
}:
mkDerivation {
  name = "exportfs";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
    libip
    libregexp
  ];
}
