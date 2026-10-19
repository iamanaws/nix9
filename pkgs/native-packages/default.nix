let
  bootstrapStdenv = import ./stdenv.nix { tools = ./tools; };
  stdenv = import ./stdenv.nix {
    tools = ./tools;
    initialPath = [ mk ];
  };
  inherit (stdenv) mkDerivation;
  libmp = import ./pkgs/libmp.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
  libsec = import ./pkgs/libsec.nix {
    inherit mkDerivation;
    src = ./libsec-source;
  };
  libbio = import ./pkgs/libbio.nix {
    mkDerivation = bootstrapStdenv.mkDerivation;
    src = ./fortune-source/sys/src/libbio;
  };
  libregexp = import ./pkgs/libregexp.nix {
    mkDerivation = bootstrapStdenv.mkDerivation;
    src = ./mk-source/sys/src/libregexp;
  };
  mk = import ./pkgs/mk.nix {
    inherit libbio libregexp;
    mkDerivation = bootstrapStdenv.mkDerivation;
    src = ./mk-source/sys/src/cmd/mk;
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
    libmp
    libsec
    libbio
    libregexp
    mk
    liblua
    mkDerivation
    stdenv
    fetchurl
    ;
  buildEnv = import ./build-env.nix { inherit mkDerivation; };
  mkShell = import ./mk-shell.nix {
    inherit stdenv;
  };
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
