let
  mkDerivation = import ./mk-derivation.nix { tools = ./tools; };
  libsec = import ./pkgs/libsec.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
  libbio = import ./pkgs/libbio.nix {
    inherit mkDerivation;
    src = ./fortune-source/sys/src/libbio;
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
    libbio
    liblua
    mkDerivation
    fetchurl
    ;
  buildEnv = import ./build-env.nix { inherit mkDerivation; };
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
  fortune = import ./pkgs/fortune.nix {
    inherit mkDerivation libbio;
    src = ./fortune-source;
  };
}
