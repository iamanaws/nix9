let
  mkDerivation = import ./mk-derivation.nix { tools = ./tools; };
  libsec = import ./pkgs/libsec.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
in
{
  inherit libsec mkDerivation;
  fetchurl = import ./pkgs/fetchurl.nix { inherit mkDerivation; };
  sha1sum = import ./pkgs/sha1sum.nix {
    inherit mkDerivation libsec;
    src = ./sha1sum.c;
  };
}
