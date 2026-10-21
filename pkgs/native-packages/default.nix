let
  bootstrapStdenv = import ./stdenv.nix { tools = ./tools; };
  stdenv = import ./stdenv.nix {
    tools = ./tools;
    initialPath = [ pkgs.mk ];
  };
  upstream = import ./pkgs/lua-source.nix;
  pkgs = rec {
    inherit stdenv;
    inherit (stdenv) mkDerivation;
    callPackage = import ./call-package.nix pkgs;
    libmp = callPackage ./pkgs/libmp.nix { src = ./libsec-source; };
    libsec = callPackage ./pkgs/libsec.nix { src = ./libsec-source; };
    libbio = callPackage ./pkgs/libbio.nix {
      mkDerivation = bootstrapStdenv.mkDerivation;
      src = ./fortune-source/sys/src/libbio;
    };
    libregexp = callPackage ./pkgs/libregexp.nix {
      mkDerivation = bootstrapStdenv.mkDerivation;
      src = ./mk-source/sys/src/libregexp;
    };
    mk = callPackage ./pkgs/mk.nix {
      mkDerivation = bootstrapStdenv.mkDerivation;
      src = ./mk-source/sys/src/cmd/mk;
    };
    yacc = callPackage ./pkgs/yacc.nix { src = ./yacc-source; };
    lex = callPackage ./pkgs/lex.nix { src = ./lex-source/sys/src/cmd/lex; };
    libl = callPackage ./pkgs/libl.nix {
      src = ./lex-source/sys/src/ape/lib/l;
      header = ./lex-source/sys/include/ape/libl.h;
    };
    fetchurl = callPackage ./pkgs/fetchurl.nix { };
    liblua = callPackage ./pkgs/liblua.nix {
      inherit upstream;
      config = ./pkgs/lua-ape-config.h;
    };
    buildEnv = callPackage ./build-env.nix { };
    mkShell = callPackage ./mk-shell.nix { };
    lua = callPackage ./pkgs/lua.nix { inherit upstream; };
    sha1sum = callPackage ./pkgs/sha1sum.nix { src = ./sha1sum.c; };
    fortune = callPackage ./pkgs/fortune.nix { src = ./fortune-source; };
  };
in
pkgs
