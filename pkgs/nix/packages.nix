let
  mkDerivation = import ./mk-derivation.nix { tools = ./tools; };
  libsec = import ./pkgs/libsec.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
  fetchurl = import ./pkgs/fetchurl.nix { inherit mkDerivation; };
in
{
  inherit libsec mkDerivation fetchurl;
  lua = import ./pkgs/lua.nix {
    inherit mkDerivation fetchurl;
    upstream = import ./pkgs/lua-source.nix;
    config = ./pkgs/lua-ape-config.h;
  };
  sha1sum = import ./pkgs/sha1sum.nix {
    inherit mkDerivation libsec;
    src = ./sha1sum.c;
  };
}
