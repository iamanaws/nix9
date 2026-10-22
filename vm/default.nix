{ pkgs, ninefront }:
rec {
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
}
