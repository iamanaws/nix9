let
  mkDerivation = import ./mk-derivation.nix { tools = ./tools; };
  libsec = import ./pkgs/libsec.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
  fetchurl = import ./pkgs/fetchurl.nix { inherit mkDerivation; };
  upstream = import ./pkgs/lua-source.nix;
  liblua = import ./pkgs/liblua.nix {
    inherit mkDerivation fetchurl upstream;
    config = ./pkgs/lua-ape-config.h;
  };
in
{
  inherit
    libsec
    liblua
    mkDerivation
    fetchurl
    ;
  lua = import ./pkgs/lua.nix {
    inherit
      mkDerivation
      fetchurl
      upstream
      liblua
      ;
  };
  sha1sum = import ./pkgs/sha1sum.nix {
    inherit mkDerivation libsec;
    src = ./sha1sum.c;
  };
}
