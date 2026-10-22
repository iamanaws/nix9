let
  rawStdenv = import ./stdenv.nix { tools = ./tools; };
  seedStdenv = import ./stdenv.nix {
    tools = ./tools;
    initialPath = [
      bootstrap.ar
      bootstrap.patch
    ];
  };
  definitions = import ./pkgs/packages.nix {
    sources = builtins.mapAttrs (name: _: ./sources + "/${name}") (builtins.readDir ./sources);
  };
  package =
    name: args:
    let
      definition = definitions.${name};
    in
    bootstrap.callPackage definition.path (definition.args // args);
  bootstrap = rec {
    buildPackages = bootstrap;
    stdenv = import ./stdenv.nix {
      tools = ./tools;
      initialPath = [
        mk
        ar
        patch
      ];
    };
    callPackage = import ./call-package.nix bootstrap;
    patch = package "patch" {
      mkDerivation = rawStdenv.mkDerivation;
      libbio = null;
    };
    ar = package "ar" {
      mkDerivation = rawStdenv.mkDerivation;
      libbio = null;
      libmach = null;
    };
    libbio = package "libbio" {
      mkDerivation = seedStdenv.mkDerivation;
    };
    libstdio = package "libstdio" {
      mkDerivation = seedStdenv.mkDerivation;
    };
    libregexp = package "libregexp" {
      mkDerivation = seedStdenv.mkDerivation;
    };
    mk = package "mk" {
      mkDerivation = seedStdenv.mkDerivation;
    };
    libc = package "libc" { };
    yacc = package "yacc" { };
    cc = package "cc" { };
  };
in
bootstrap
