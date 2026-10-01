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
      testSupport = pkgs.lib.fileset.toSource {
        root = ./tests;
        fileset = pkgs.lib.fileset.fileFilter (file: file.hasExt "py") ./tests;
      };
      sysroot =
        pkgs.runCommand "9front-11952-amd64-sysroot"
          {
            requiredSystemFeatures = [ "kvm" ];
          }
          ''
            ${python}/bin/python ${testSupport}/export_sysroot.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 "$TMPDIR/sysroot.tar"
            mkdir -p "$out"
            tar -xf "$TMPDIR/sysroot.tar" -C "$out"
            test -s "$out/amd64/lib/libc.a"
            test -s "$out/sys/include/libc.h"
          '';
      helloC =
        pkgs.runCommand "hello-c-native-9front-amd64"
          {
            requiredSystemFeatures = [ "kvm" ];
            nativeBuildInputs = [ pkgs.go ];
          }
          ''
            ${python}/bin/python ${testSupport}/build_c.py \
              ${pkgs.qemu}/bin/qemu-system-x86_64 \
              ${vm}/9front.qcow2 ${./pkgs/hello-c-native} "$out"
            export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
            go run ${./tests/format.go} "$out/bin/hello-c"
          '';
      helloCross = pkgs.callPackage ./pkgs/hello-c-cross { inherit cTools sysroot; };
      smoke = pkgs.writeShellApplication {
        name = "smoke-test";
        text = ''
          exec ${python}/bin/python ${testSupport}/smoke.py \
            ${pkgs.qemu}/bin/qemu-system-x86_64 \
            ${vm}/9front.qcow2 ${hello}/bin/hello \
            'Hello from Nix on plan9/amd64!' "$@"
        '';
      };
      smokeC = pkgs.writeShellApplication {
        name = "smoke-test-c";
        text = ''
          exec ${python}/bin/python ${testSupport}/smoke.py \
            ${pkgs.qemu}/bin/qemu-system-x86_64 \
            ${vm}/9front.qcow2 ${helloC}/bin/hello-c \
            'Hello from Nix-built C on 9front/amd64!' "$@"
        '';
      };
      smokeCross = pkgs.writeShellApplication {
        name = "smoke-test-c-cross";
        text = ''
          exec ${python}/bin/python ${testSupport}/smoke.py \
            ${pkgs.qemu}/bin/qemu-system-x86_64 \
            ${vm}/9front.qcow2 ${helloCross}/bin/hello-c \
            'Hello from Nix-built C on 9front/amd64!' "$@"
        '';
      };
    in
    {
      packages.${system} = {
        default = hello;
        hello-plan9 = hello;
        hello-c-native = helloC;
        hello-c-cross = helloCross;
        goken9cc = cTools;
        sysroot = sysroot;
        vm-image = vm;
        setup-vm = setup;
        run-vm = run;
        smoke-test = smoke;
        smoke-test-c = smokeC;
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
            smoke-test-c = smokeC;
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
          pkgs.nixfmt
        ];
      };
      formatter.${system} = pkgs.nixfmt;
    };
}
