let
  bootstrap = import ./bootstrap.nix;
  buildStdenv = import ./stdenv.nix {
    tools = ./tools;
    inherit (bootstrap) cc libc;
    initialPath = [
      bootstrap.mk
      bootstrap.ar
      bootstrap.patch
    ];
  };
  stdenv = import ./stdenv.nix {
    tools = ./tools;
    shell = "${pkgs.rc}/bin/rc";
    inherit (pkgs) cc libc;
    initialPath = [
      pkgs.mk
      pkgs.ar
      pkgs.rc
      pkgs.patch
    ];
  };
  upstream = import ./pkgs/lua-source.nix;
  pkgs = rec {
    inherit stdenv;
    inherit (stdenv) mkDerivation;
    callPackage = import ./call-package.nix pkgs;
    cc = bootstrap.cc;
    ar = bootstrap.ar;
    patch = bootstrap.patch;
    rc = callPackage ./pkgs/rc.nix {
      stdenv = buildStdenv;
      yacc = bootstrap.yacc;
      src = ./rc-source;
    };
    libc = callPackage ./pkgs/libc.nix {
      stdenv = buildStdenv;
      src = ./libc-source;
    };
    libmp = callPackage ./pkgs/libmp.nix { src = ./libsec-source; };
    libsec = callPackage ./pkgs/libsec.nix { src = ./libsec-source; };
    libbio = callPackage ./pkgs/libbio.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./fortune-source/sys/src/libbio;
    };
    libregexp = callPackage ./pkgs/libregexp.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./mk-source/sys/src/libregexp;
    };
    mk = callPackage ./pkgs/mk.nix {
      mkDerivation = buildStdenv.mkDerivation;
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
