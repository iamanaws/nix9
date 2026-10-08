{
  description = "Experiments in Nix-managed cross compilation for 9front";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    ninefront = {
      url = "github:majiru/9front-in-a-box";
      flake = false;
    };
    goken9cc = {
      url = "github:aryx/goken9cc/e549ce5515ac036ea757d1ebc660686e59ccc35b";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      ninefront,
      goken9cc,
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      hello = pkgs.callPackage ./pkgs/hello-plan9 { };
      cTools = pkgs.callPackage ./pkgs/goken9cc { source = goken9cc; };
      # Reuse upstream's pinned release and serial-console preparation.
      vm = (pkgs.callPackage (ninefront + "/vm.nix") { }).overrideAttrs (old: {
        requiredSystemFeatures = (old.requiredSystemFeatures or [ ]) ++ [ "kvm" ];
      });
      setup = pkgs.writeShellApplication {
        name = "setup-vm";
        runtimeInputs = [ pkgs.qemu ];
        text = ''
          disk="''${1:-9front.hjfs.amd64.qcow2}"
          if [[ -e "$disk" || -L "$disk" ]]; then
            echo "Refusing to replace existing disk: $disk" >&2
            exit 1
          fi
          qemu-img create -f qcow2 -F qcow2 -b ${vm}/9front.qcow2 "$disk"
        '';
      };
      run = pkgs.writeShellApplication {
        name = "run-vm";
        runtimeInputs = [ pkgs.qemu ];
        text = ''
          disk="''${1:-9front.hjfs.amd64.qcow2}"
          if [[ ! -f "$disk" ]]; then
            echo "Run nix run .#setup-vm first (missing $disk)" >&2
            exit 1
          fi
          exec qemu-system-x86_64 -enable-kvm -m 2G -smp 2 \
            -display none -monitor none -serial stdio \
            -drive "file=$disk,format=qcow2,if=virtio" -nic user
        '';
      };
      python = pkgs.python3.withPackages (p: [ p.pexpect ]);
      nixUtil = pkgs.callPackage ./pkgs/nix { };
      nixProbe = pkgs.callPackage ./tests/libutil { inherit nixUtil; };
      testSupport =
        files:
        pkgs.lib.fileset.toSource {
          root = ./tests;
          fileset = pkgs.lib.fileset.unions ([ ./tests/guest.py ] ++ files);
        };
      sysroot =
        pkgs.runCommand "9front-11952-amd64-sysroot"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${
              testSupport [
                ./tests/export_tree.py
                ./tests/artifacts.py
              ]
            }/export_tree.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 "$TMPDIR/sysroot.tar" sys/include amd64/include amd64/lib
            mkdir -p "$out"
            tar -xf "$TMPDIR/sysroot.tar" -C "$out"
            test -s "$out/amd64/lib/libc.a"
            test -s "$out/sys/include/libc.h"
          '';
      nativeTools = pkgs.runCommand "9front-native-tools" { requiredSystemFeatures = [ "kvm" ]; } ''
        ${python}/bin/python ${
          testSupport [
            ./tests/export_tree.py
            ./tests/artifacts.py
          ]
        }/export_tree.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
          "$TMPDIR/tools.tar" amd64/bin/6a amd64/bin/6c amd64/bin/6l amd64/bin/ar amd64/bin/awk \
          amd64/bin/bind amd64/bin/cpp amd64/bin/pcc amd64/bin/tar amd64/bin/gunzip \
          amd64/bin/cat amd64/bin/sed amd64/bin/webfs amd64/bin/cp amd64/bin/echo amd64/bin/mpc amd64/bin/rc amd64/bin/mkdir amd64/bin/test rc/lib/rcmain
        tar -xf "$TMPDIR/tools.tar"
        mkdir -p "$out/bin" "$out/sys" "$out/amd64/lib"
        cp amd64/bin/* "$out/bin/"
        cp rc/lib/rcmain "$out/rcmain"
        cp -r ${sysroot}/sys/include "$out/sys/"
        cp -r ${sysroot}/amd64/include "$out/amd64/"
        cp ${libc}/lib/libc.a "$out/amd64/lib/"
        mkdir -p "$out/amd64/lib/ape"
        cp ${libap}/lib/libap.a ${libbsd}/lib/libbsd.a "$out/amd64/lib/ape/"
      '';
      nativePackages = pkgs.runCommand "native-package-inputs" { } ''
        mkdir "$out"
        cp -r ${secSource} "$out/libsec"
        cp ${./pkgs/libsec/native.nix} "$out/libsec.nix"
        cp ${./pkgs/sha1sum/native.nix} "$out/sha1sum.nix"
        cp ${./lib/mk-derivation.nix} "$out/mk-derivation.nix"
        cp ${sha1sum.source} "$out/sha1sum.c"
        cp ${sha1sum}/bin/sha1sum "$out/cross"
      '';
      nixUtilTests =
        pkgs.runCommand "nix-util-tests"
          {
            SODIUM_LIBRARY = "${pkgs.libsodium}/lib/libsodium.so";
            requiredSystemFeatures = [ "kvm" ];
            nativeBuildInputs = [
              pkgs.nix
              pkgs.brotli
              pkgs.zstd
              pkgs.openssl
            ];
          }
          ''
            ${python}/bin/python ${
              testSupport [
                ./tests/libutil.py
                ./tests/nix_store.py
                ./tests/nix_eval.py
                ./tests/nix_build.py
                ./tests/nix_build_cli.py
                ./tests/nix-build.nix
                ./tests/nix_concurrency.py
                ./tests/concurrent-builds.nix
                ./tests/c_abi.py
                ./tests/sha1sum.py
                ./tests/libutil_compression.py
                ./tests/libutil_keys.py
                ./tests/artifacts.py
              ]
            }/libutil.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
              ${nixUtil.cc9.elf2aout} ${nixProbe}/probe.elf ${nixUtil}/nix-store.elf ${nixUtil}/nix-instantiate.elf ${nixUtil}/nix-build.elf \
              ${./pkgs/hello-c-cross} ${./tests/c-abi} ${nativePackages} ${nativeTools} "$out"
            ${python}/bin/python ${
              testSupport [
                ./tests/native_install.py
                ./tests/native_fetch.py
                ./tests/native_sources.py
                ./tests/native_recovery.py
                ./tests/native_transfer.py
                ./tests/native_cache.py
                ./tests/native_cache_network.py
                ./tests/artifacts.py
                ./tests/recovery.nix
                ./tests/sources.nix
                ./tests/isolation.nix
                ./tests/lua.py
                ./tests/lua
                ./tests/fetch.nix
              ]
            }/native_install.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
              ${nixPackage} ${nixPackage.guestPrefix} "$out" ${lua.archive} \
              ${nixProbe}/probe.elf ${nixUtil.cc9.elf2aout}
          '';
      mkPlan9Program = import ./lib/mk-plan9-program.nix {
        inherit
          pkgs
          cTools
          sysroot
          libc
          ;
      };
      helloCross = pkgs.callPackage ./pkgs/hello-c-cross { inherit mkPlan9Program; };
      sha1sum = pkgs.callPackage ./pkgs/sha1sum { inherit mkPlan9Program libsec; };
      sha1sumTests =
        pkgs.runCommand "sha1sum-tests"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport [ ./tests/sha1sum.py ]}/sha1sum.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 ${sha1sum.source} ${sha1sum}/bin/sha1sum "$out"
          '';
      abiCross = pkgs.callPackage ./tests/c-abi { inherit cTools sysroot libc; };
      apeCross = pkgs.callPackage ./tests/ape {
        inherit
          cTools
          sysroot
          libap
          libbsd
          ;
      };
      apeSource =
        pkgs.runCommand "9front-ape-source"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${
              testSupport [
                ./tests/export_tree.py
                ./tests/artifacts.py
              ]
            }/export_tree.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 "$TMPDIR/source.tar" \
              sys/src/ape sys/src/libc
            mkdir -p "$out"
            tar -xf "$TMPDIR/source.tar" -C "$out"
          '';
      libbsd = pkgs.callPackage ./pkgs/libbsd {
        inherit cTools sysroot;
        source = apeSource;
      };
      libap = pkgs.callPackage ./pkgs/libap {
        inherit cTools sysroot;
        source = apeSource;
      };
      libc = pkgs.callPackage ./pkgs/libc {
        inherit cTools sysroot;
        source = apeSource;
      };
      secSource = pkgs.runCommand "9front-libsec-source" { requiredSystemFeatures = [ "kvm" ]; } ''
        ${python}/bin/python ${
          testSupport [
            ./tests/export_tree.py
            ./tests/artifacts.py
          ]
        }/export_tree.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 "$TMPDIR/source.tar" \
          sys/src/libsec sys/src/libmp sys/src/cmd/mpc.y
        mkdir -p "$out"
        tar -xf "$TMPDIR/source.tar" -C "$out"
      '';
      mpc = pkgs.callPackage ./pkgs/mpc { source = secSource; };
      libmp = pkgs.callPackage ./pkgs/libmp {
        inherit cTools sysroot;
        source = secSource;
      };
      libsec = pkgs.callPackage ./pkgs/libsec {
        inherit cTools sysroot mpc;
        source = secSource;
      };
      secCross = pkgs.callPackage ./tests/libsec {
        inherit
          cTools
          sysroot
          libc
          libsec
          libmp
          ;
      };
      secTests = pkgs.runCommand "libsec-tests" { requiredSystemFeatures = [ "kvm" ]; } ''
        ${python}/bin/python ${testSupport [ ./tests/libsec.py ]}/libsec.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 ${secCross} "$out"
      '';
      lua = pkgs.callPackage ./pkgs/lua {
        inherit
          cTools
          sysroot
          libbsd
          libap
          ;
      };
      libbz2 = pkgs.callPackage ./pkgs/libbz2 { inherit cTools sysroot; };
      mkGuestPackage = import ./lib/mk-guest-package.nix { inherit pkgs; };
      luaPackage = mkGuestPackage {
        name = "lua-${lua.version}";
        package = lua;
      };
      sha1sumPackage = mkGuestPackage {
        name = "sha1sum-${builtins.substring 0 12 sha1sum.revision}";
        package = sha1sum;
      };
      mkGuestEnvironment = import ./lib/mk-guest-environment.nix { inherit pkgs; };
      nativeNix = pkgs.callPackage ./pkgs/nix/package.nix {
        inherit
          nixUtil
          nativeTools
          secSource
          sha1sum
          ;
      };
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
      development = pkgs.callPackage ./pkgs/guest-development {
        inherit
          sysroot
          libc
          libap
          libbsd
          ;
      };
      developmentPackage = mkGuestPackage {
        name = "c-development-11952";
        package = development;
      };
      guestDevelopment = mkGuestEnvironment {
        name = "development";
        packages = [ developmentPackage ];
      };
      developmentTests =
        pkgs.runCommand "guest-development-tests" { requiredSystemFeatures = [ "kvm" ]; }
          ''
            ${python}/bin/python ${
              testSupport [
                ./tests/guest_development.py
                ./tests/c_abi.py
                ./tests/ape.py
              ]
            }/guest_development.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
              ${guestDevelopment} ${guestDevelopment.guestPrefix} ${development.guestPrefix} \
              ${./pkgs/hello-c-cross/main.c} ${./tests/c-abi} ${./tests/ape/main.c} \
              ${./tests/guest-development/bsd.c} "$out"
          '';
      packageTests = pkgs.runCommand "package-tests" { requiredSystemFeatures = [ "kvm" ]; } ''
        ${python}/bin/python ${testSupport [ ./tests/install_packages.py ]}/install_packages.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
          ${guestEnvironment} ${guestEnvironment.guestPrefix} \
          ${luaPackage.guestPrefix} ${sha1sumPackage.guestPrefix} \
          ${./tests/lua/fixture.lua} "$out"
      '';
      libbz2Consumer = pkgs.callPackage ./tests/libbz2 {
        inherit
          cTools
          sysroot
          libbz2
          libap
          libbsd
          ;
      };
      libbz2Tests =
        pkgs.runCommand "libbz2-tests"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport [ ./tests/libbz2.py ]}/libbz2.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
              ${libbz2.source} ${libbz2} ${libbz2Consumer} ${./tests/libbz2/main.c} "$out"
          '';
      luaTests =
        pkgs.runCommand "lua-tests"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport [ ./tests/lua.py ]}/lua.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 ${lua.source} ${lua}/bin/lua ${./tests/lua} \
              ${guestDevelopment} ${guestDevelopment.guestPrefix} ${development.guestPrefix} "$out"
          '';
      apeTests =
        pkgs.runCommand "ape-tests"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport [ ./tests/ape.py ]}/ape.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 ${./tests/ape/main.c} ${apeCross}/bin/ape-tests "$out"
          '';
      abiTests =
        pkgs.runCommand "c-abi-tests"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport [ ./tests/c_abi.py ]}/c_abi.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 ${./tests/c-abi} ${abiCross} "$out"
          '';
      smoke = pkgs.writeShellApplication {
        name = "smoke-test";
        text = ''
          exec ${python}/bin/python ${testSupport [ ./tests/smoke.py ]}/smoke.py \
            ${pkgs.qemu}/bin/qemu-system-x86_64 \
            ${vm}/9front.qcow2 ${hello}/bin/hello \
            'Hello from Nix on plan9/amd64!' "$@"
        '';
      };
      smokeCross = pkgs.writeShellApplication {
        name = "smoke-test-c-cross";
        text = ''
          exec ${python}/bin/python ${testSupport [ ./tests/smoke.py ]}/smoke.py \
            ${pkgs.qemu}/bin/qemu-system-x86_64 \
            ${vm}/9front.qcow2 ${helloCross}/bin/hello-c \
            'Hello from Nix-built C on 9front/amd64!' "$@"
        '';
      };
    in
    {
      lib.mkPlan9Program = mkPlan9Program;
      lib.mkDerivation = import ./lib/mk-derivation.nix;
      lib.mkGuestPackage = mkGuestPackage;
      lib.mkGuestEnvironment = mkGuestEnvironment;
      packages.${system} = {
        default = hello;
        hello-plan9 = hello;
        hello-c-cross = helloCross;
        inherit sha1sum;
        sha1sum-tests = sha1sumTests;
        c-abi-cross = abiCross;
        ape-cross = apeCross;
        ape-tests = apeTests;
        inherit lua;
        native-tools = nativeTools;
        nix-util = nixUtil;
        nix-util-tests = nixUtilTests;
        lua-package = luaPackage;
        sha1sum-package = sha1sumPackage;
        package-tests = packageTests;
        guest-environment = guestEnvironment;
        guest-development = guestDevelopment;
        nix = nativeNix;
        nix-package = nixPackage;
        guest-development-tests = developmentTests;
        inherit libbz2;
        inherit libbsd;
        inherit libap;
        inherit libc;
        inherit libsec;
        inherit libmp;
        inherit mpc;
        libsec-tests = secTests;
        libbz2-tests = libbz2Tests;
        lua-tests = luaTests;
        c-abi-tests = abiTests;
        goken9cc = cTools;
        sysroot = sysroot;
        vm-image = vm;
        setup-vm = setup;
        run-vm = run;
        smoke-test = smoke;
        smoke-test-c-cross = smokeCross;
      };
      apps.${system} =
        builtins.mapAttrs
          (_: package: {
            type = "app";
            meta.description = "9front experiment: ${package.meta.mainProgram}";
            program = "${package}/bin/${package.meta.mainProgram}";
          })
          {
            setup-vm = setup;
            run-vm = run;
            smoke-test = smoke;
            smoke-test-c-cross = smokeCross;
          };
      checks.${system}.hello-format =
        pkgs.runCommand "hello-plan9-format"
          {
            nativeBuildInputs = [ pkgs.go ];
          }
          ''
            export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
            go run ${./tests/format.go} ${hello}/bin/hello
            touch "$out"
          '';
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.go
          pkgs.qemu
          python
          pkgs.nixfmt-tree
        ];
      };
      formatter.${system} = pkgs.nixfmt-tree;
    };
}
