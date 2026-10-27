{
  stdenv,
  src,
  lib9p,
  libauth,
  libthread,
  libsec,
  libmp,
}:
stdenv.mkDerivation {
  name = "webfs";
  inherit src;
  buildInputs = [
    lib9p
    libauth
    libthread
    libsec
    libmp
  ];
  meta.description = "HTTP and HTTPS file system";
}
