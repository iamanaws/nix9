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
  definitions = import ./pkgs/packages.nix {
    sources = builtins.mapAttrs (name: _: ./sources + "/${name}") (builtins.readDir ./sources);
  };
  overrides = {
    buildTools = {
      stdenv = buildStdenv;
      inherit (bootstrap) libbio libregexp;
    };
    cc.stdenv = toolchainStdenv;
    ar = {
      mkDerivation = buildStdenv.mkDerivation;
      buildPackages = pkgs // {
        patch = bootstrap.patch;
      };
    };
    patch.mkDerivation = toolchainStdenv.mkDerivation;
    rc = {
      stdenv = buildStdenv;
      buildPackages = bootstrap;
    };
    libc.stdenv = buildStdenv;
    libString.mkDerivation = buildStdenv.mkDerivation;
    libflate.mkDerivation = buildStdenv.mkDerivation;
    awkMaketab = {
      mkDerivation = buildStdenv.mkDerivation;
      buildPackages = bootstrap;
    };
    libbio.mkDerivation = buildStdenv.mkDerivation;
    libstdio.mkDerivation = buildStdenv.mkDerivation;
    libmach.mkDerivation = buildStdenv.mkDerivation;
    libregexp.mkDerivation = buildStdenv.mkDerivation;
    mk.mkDerivation = buildStdenv.mkDerivation;
    yacc.stdenv = toolchainStdenv;
    libap.stdenv = buildStdenv;
    libbsd.stdenv = buildStdenv;
  };
  pkgs =
    builtins.mapAttrs (
      name: definition: pkgs.callPackage definition.path (definition.args // (overrides.${name} or { }))
    ) definitions
    // {
      inherit stdenv;
      buildPackages = pkgs;
      inherit (stdenv) mkDerivation;
      callPackage = import ./call-package.nix pkgs;
      fetchgit = pkgs.callPackage ./pkgs/fetchgit { };
      fetchurl = pkgs.callPackage ./pkgs/fetchurl { };
      buildEnv = pkgs.callPackage ./build-env.nix { };
      mkShell = pkgs.callPackage ./mk-shell.nix { };
    };
in
pkgs
