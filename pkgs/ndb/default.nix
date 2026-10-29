{
  mkDerivation,
  src,
  libndb,
  libauth,
  libauthsrv,
}:
mkDerivation {
  name = "ndb";
  inherit src;
  buildInputs = [
    libndb
    libauth
    libauthsrv
  ];
  buildFlags = [ "all" ];
  installPhase = ''
    mkdir -p $out/bin/ndb
    for(command in mkdb query mkhash mkhosts cs csquery dns dnsquery dnsdebug dnsgetip ipquery inform) {
      cp 6.$command $out/bin/ndb/$command
    }
  '';
}
