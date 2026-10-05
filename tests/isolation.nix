{ packages }:
let
  pkgs = import packages;
in
pkgs.mkDerivation {
  name = "namespace-isolation";
  buildCommand = ''
    for(directory in /bin /amd64/bin /rc/bin /rc/lib /sys/include /amd64/include /amd64/lib) {
      /bin/test ! -e $directory/nix9-host-only
    }
    /bin/test -s /sys/include/libc.h
    /bin/test -s /amd64/lib/ape/libap.a
    /bin/rc -e -c 'test ! -e /rc/lib/nix9-host-only; echo namespace-isolated' > $out
  '';
}
