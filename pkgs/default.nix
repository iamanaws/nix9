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
    cross = {
      libbio = callPackage ./libbio { source = sources.fortuneSource; };
      libregexp = callPackage ./libregexp { source = sources.mkSource; };
      mk = callPackage ./mk { source = sources.mkSource; };
      yacc = callPackage ./yacc { source = sources.yaccSource; };
      rc = callPackage ./rc { source = sources.rcSource; };
      cc = callPackage ./cc { source = sources.ccSource; };
      libmach = callPackage ./libmach { source = sources.machSource; };
      ar = callPackage ./ar { source = sources.ccSource; };
      sha1sum = callPackage ./sha1sum { };
      libbsd = callPackage ./libbsd { source = sources.apeSource; };
      libap = callPackage ./libap { source = sources.apeSource; };
      libc = callPackage ./libc { source = sources.apeSource; };
      mpc = callPackage ./mpc { source = sources.secSource; };
      libthread = callPackage ./libthread { source = sources.ramfsSource; };
      clone = callPackage ./clone { };
      libmp = callPackage ./libmp { source = sources.secSource; };
      libsec = callPackage ./libsec { source = sources.secSource; };
      lua = callPackage ./lua { };
      libbz2 = callPackage ./libbz2 { };
    };
    inherit (cross) lua sha1sum;
  in
  support
  // vmTools
  // sources
  // cross
  // rec {
    imageTools = callPackage ./native-packages/image-tools.nix { };
    nativeTools = callPackage ./native-packages/tools.nix { };
    nativeBootstrap = callPackage ./bootstrap.nix { };
    hello = callPackage ./hello-plan9 { };
    cTools = callPackage ./goken9cc { source = goken9cc; };
    nixUtil = callPackage ./nix { };
    mkPlan9Program = callPackage ../lib/mk-plan9-program.nix { };
    helloCross = callPackage ./hello-c-cross { };
    mkPlan9Library = callPackage ../lib/mk-plan9-library.nix { };
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
    nativePackageSet = callPackage ./native-packages/package.nix { libcSource = sources.apeSource; };
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
