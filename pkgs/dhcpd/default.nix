{
  mkDerivation,
  src,
  libndb,
}:
mkDerivation {
  name = "dhcpd";
  inherit src;
  buildInputs = [ libndb ];
  sourceRoot = "source/sys/src/cmd/ip/dhcpd";
  buildFlags = [ "all" ];
  installPhase = ''
    mkdir -p $out/bin/ip
    cp 6.dhcpd $out/bin/ip/dhcpd
    cp 6.dhcpleases $out/bin/ip/dhcpleases
  '';
}
