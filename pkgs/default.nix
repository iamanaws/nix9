{
  pkgs,
  ninefront,
  goken9cc,
}:
pkgs.lib.makeScope pkgs.newScope (
  self:
  let
    inherit (self) callPackage;
    support = import ../tests/support.nix { inherit pkgs; };
    vmTools = import ../vm { inherit pkgs ninefront; };
    inherit (vmTools) vm setup run;
    sources = import ./sources.nix {
      inherit pkgs vm;
      inherit (support) python testSupport;
    };
    buildPackages = pkgs // {
      awkMaketab = pkgs.callPackage ./awk-maketab/build.nix { source = sources.buildToolsSource; };
      yacc = pkgs.runCommand "build-yacc" { } ''
        mkdir -p "$out/bin"
        ln -s ${pkgs.plan9port}/plan9/bin/yacc "$out/bin/yacc"
      '';
      mpc = callPackage ./mpc/build.nix {
        source = sources.secSource;
        inherit (pkgs) stdenv;
      };
    };
    luaSource = import ./lua/source.nix;
    luaPrefix = "/usr/local/pkg/lua-${luaSource.version}";
    checksumSource = callPackage ./sha1sum/source.nix { };
    packageDefinitions = import ./packages.nix { inherit sources; };
    packages = builtins.mapAttrs (
      _: definition: callPackage definition.path definition.args
    ) packageDefinitions;
    cross = builtins.removeAttrs packages [ "buildTools" ] // {
      build-tools = packages.buildTools;
      libc = packages.libc.override { stdenv = callPackage ./stdenv { libc = null; }; };
      liblua = packages.liblua.override { runtimePrefix = luaPrefix; };
      sha1sum = packages.sha1sum.overrideAttrs (_: {
        passthru = checksumSource;
      });
      lua = packages.lua.overrideAttrs (_: {
        passthru = {
          inherit (luaSource) version;
          archive = pkgs.fetchurl luaSource.src;
          guestPrefix = luaPrefix;
          source = pkgs.callPackage ./lua/prepare-source.nix {
            upstream = luaSource;
            runtimePrefix = luaPrefix;
          };
        };
      });
    };
    inherit (cross) lua sha1sum;
  in
  support
  // vmTools
  // sources
  // cross
  // rec {
    inherit buildPackages sources packageDefinitions;
    stdenv = callPackage ./stdenv { };
    inherit (stdenv) mkDerivation mkShell;
    buildTools = cross.build-tools;
    imageTools = callPackage ./native-packages/image-tools.nix { };
    nativeTools = callPackage ./native-packages/tools.nix { };
    nativeBootstrap = callPackage ./bootstrap.nix { };
    hello = callPackage ./hello-plan9 { };
    cTools = callPackage ./goken9cc {
      source = goken9cc;
      inherit (pkgs) stdenv;
    };
    nixUtil = callPackage ./nix { };
    mkPlan9Program = callPackage ../lib/mk-plan9-program.nix { };
    helloCross = callPackage ./hello-c-cross { src = ./hello-c-cross/main.c; };
    mkGuestPackage = import ../lib/mk-guest-package.nix { inherit pkgs; };
    luaPackage = mkGuestPackage {
      name = "lua-${lua.version}";
      package = lua;
    };
    sha1sumPackage = mkGuestPackage {
      name = "sha1sum-${builtins.substring 0 12 sha1sum.revision}";
      package = sha1sum;
    };
    mkGuestEnvironment = import ../lib/mk-guest-environment.nix { inherit pkgs; };
    nativeNix = callPackage ./nix/package.nix { };
    nativePackageSet = callPackage ./native-packages/package.nix { };
    nativePackagesArchive = mkGuestPackage {
      name = "native-packages";
      package = nativePackageSet;
    };
    nativePackageSource =
      pkgs.runCommand "native-package-source" { nativeBuildInputs = [ pkgs.nix ]; }
        ''
          mkdir -p "$out"
          tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
            --hard-dereference --transform='s,^\.,packages,' -C ${nativePackageSet} -cf - . \
            | gzip -n > "$out/packages.tar.gz"
          nix --extra-experimental-features nix-command hash path ${nativePackageSet} > "$out/sha256"
          substitute ${../examples/update.nix} "$out/update.nix" \
            --replace-fail '@sha256@' "$(cat "$out/sha256")"
        '';
    nixPackage = mkGuestPackage {
      name = "nix-${nixUtil.version}";
      package = nativeNix;
    };
    guestEnvironment = mkGuestEnvironment {
      name = "default";
      packages = [
        luaPackage
        sha1sumPackage
      ];
    };
    development = callPackage ./guest-development { };
    developmentPackage = mkGuestPackage {
      name = "c-development-11952";
      package = development;
    };
    guestDevelopment = mkGuestEnvironment {
      name = "development";
      packages = [ developmentPackage ];
    };
    flakePackages = cross // {
      inherit (sources) sysroot;
      default = hello;
      hello-plan9 = hello;
      hello-c-cross = helloCross;
      native-tools = nativeTools;
      nix-util = nixUtil;
      lua-package = luaPackage;
      sha1sum-package = sha1sumPackage;
      guest-environment = guestEnvironment;
      guest-development = guestDevelopment;
      nix = nativeNix;
      nix-package = nixPackage;
      native-packages = nativePackagesArchive;
      native-package-source = nativePackageSource;
      native-bootstrap = nativeBootstrap;
      goken9cc = cTools;
      vm-image = vm;
      setup-vm = setup;
      run-vm = run;
    };
  }
)
