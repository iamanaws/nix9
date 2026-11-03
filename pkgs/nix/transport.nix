{
  mkDerivation,
  libauth,
  libauthsrv,
  libsec,
  libmp,
  libbio,
}:
mkDerivation {
  name = "nix-store-service";
  src = ./.;
  buildInputs = [
    libauth
    libauthsrv
    libsec
    libmp
    libbio
  ];
  buildCommand = ''
    mkdir -p $out/bin
    6c -o service.6 $src/service.c
    6l -o $out/bin/nix-store-service service.6
  '';
}
