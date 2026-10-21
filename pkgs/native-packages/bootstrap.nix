let
  rawStdenv = import ./stdenv.nix { tools = ./tools; };
  seedStdenv = import ./stdenv.nix {
    tools = ./tools;
    initialPath = [ bootstrap.ar ];
  };
  bootstrap = rec {
    stdenv = import ./stdenv.nix {
      tools = ./tools;
      initialPath = [
        mk
        ar
      ];
    };
    callPackage = import ./call-package.nix bootstrap;
    ar = callPackage ./pkgs/ar.nix {
      mkDerivation = rawStdenv.mkDerivation;
      src = ./ar.c;
    };
    libbio = callPackage ./pkgs/libbio.nix {
      mkDerivation = seedStdenv.mkDerivation;
      src = ./fortune-source/sys/src/libbio;
    };
    libregexp = callPackage ./pkgs/libregexp.nix {
      mkDerivation = seedStdenv.mkDerivation;
      src = ./mk-source/sys/src/libregexp;
    };
    mk = callPackage ./pkgs/mk.nix {
      mkDerivation = seedStdenv.mkDerivation;
      src = ./mk-source/sys/src/cmd/mk;
    };
    libc = callPackage ./pkgs/libc.nix { src = ./libc-source; };
    yacc = callPackage ./pkgs/yacc.nix { src = ./yacc-source; };
    cc = callPackage ./pkgs/cc.nix { src = ./cc-source; };
  };
in
bootstrap
