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
  toolchainStdenv = import ./stdenv.nix {
    tools = ./tools;
    shell = "${pkgs.rc}/bin/rc";
    cc = bootstrap.cc;
    libc = pkgs.libc;
    initialPath = [
      pkgs.mk
      pkgs.ar
      pkgs.rc
    ];
  };
  stdenv = import ./stdenv.nix {
    tools = ./tools;
    shell = "${pkgs.rc}/bin/rc";
    inherit (pkgs) cc libc;
    initialPath = with pkgs; [
      mk
      ar
      rc
      patch
      buildTools
    ];
  };
  upstream = import ./pkgs/lua-source.nix;
  pkgs = rec {
    inherit stdenv;
    inherit (stdenv) mkDerivation;
    callPackage = import ./call-package.nix pkgs;
    buildTools = callPackage ./pkgs/build-tools/native.nix {
      stdenv = buildStdenv;
      src = ./build-tools-source;
      inherit (bootstrap) yacc libbio libregexp;
    };
    cc = callPackage ./pkgs/cc.nix {
      stdenv = toolchainStdenv;
      src = ./cc-source;
    };
    ar =
      (callPackage ./pkgs/ar.nix {
        mkDerivation = buildStdenv.mkDerivation;
        src = ./ar.c;
        patch = bootstrap.patch;
      }).overrideAttrs
        (_: {
          buildInputs = [
            libbio
            libmach
          ];
        });
    patch =
      (callPackage ./pkgs/patch.nix {
        mkDerivation = toolchainStdenv.mkDerivation;
        src = ./patch.c;
      }).overrideAttrs
        (_: {
          buildInputs = [ libbio ];
        });
    rc = callPackage ./pkgs/rc.nix {
      stdenv = buildStdenv;
      yacc = bootstrap.yacc;
      src = ./rc-source;
    };
    libc = callPackage ./pkgs/libc.nix {
      stdenv = buildStdenv;
      src = ./libc-source;
    };
    libflate = callPackage ./pkgs/libflate.nix { src = ./git-source/sys/src/libflate; };
    git = callPackage ./pkgs/git.nix {
      src = ./git-source/sys/src/cmd/git;
      exporter = ./pkgs/git-export-tree.c;
    };
    lib9p = callPackage ./pkgs/lib9p.nix { src = ./ramfs-source/sys/src/lib9p; };
    libauth = callPackage ./pkgs/libauth.nix { src = ./ramfs-source/sys/src/libauth; };
    libthread = callPackage ./pkgs/libthread.nix { src = ./ramfs-source/sys/src/libthread; };
    ramfs = callPackage ./pkgs/ramfs.nix { src = ./ramfs-source/sys/src/cmd/ramfs.c; };
    libmp = callPackage ./pkgs/libmp.nix { src = ./libsec-source; };
    libsec = callPackage ./pkgs/libsec.nix { src = ./libsec-source; };
    libbio = callPackage ./pkgs/libbio.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./fortune-source/sys/src/libbio;
    };
    libmach = callPackage ./pkgs/libmach.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./libmach-source;
    };
    libregexp = callPackage ./pkgs/libregexp.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./mk-source/sys/src/libregexp;
    };
    mk = callPackage ./pkgs/mk.nix {
      mkDerivation = buildStdenv.mkDerivation;
      src = ./mk-source/sys/src/cmd/mk;
    };
    yacc = callPackage ./pkgs/yacc.nix {
      stdenv = toolchainStdenv;
      src = ./yacc-source;
    };
    lex = callPackage ./pkgs/lex.nix { src = ./lex-source/sys/src/cmd/lex; };
    libl = callPackage ./pkgs/libl.nix {
      src = ./lex-source/sys/src/ape/lib/l;
      header = ./lex-source/sys/include/ape/libl.h;
    };
    fetchgit = callPackage ./pkgs/fetchgit.nix { };
    clone = callPackage ./pkgs/clone.nix { upstream = import ./pkgs/clone-source.nix; };
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
