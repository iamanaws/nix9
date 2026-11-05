{
  pkgs,
  python,
  vm,
  nativeBootstrap,
}:
let
  bootstrap = nativeBootstrap.override {
    cachePackages = [
      "auth"
      "cwfs"
      "rcpu"
      "ndb"
      "rc"
      "namespaceTools"
      "listen"
    ];
  };
  source = pkgs.linkFarm "nix9-lab-source" (
    map
      (path: {
        name = baseNameOf path;
        inherit path;
      })
      [
        ./lab.py
        ./provision.py
        ./configuration.nix
        ../../tests/guest.py
        ../../tests/ethernet.py
        ../../tests/boot_medium.py
      ]
  );
in
pkgs.writeShellApplication {
  name = "lab";
  runtimeInputs = [ pkgs.mtools ];
  text = ''
    export PYTHONPATH=${source}
    export NIX9_LAB_QEMU=${pkgs.qemu}/bin/qemu-system-x86_64
    export NIX9_LAB_IMAGE=${vm}
    export NIX9_LAB_BOOTSTRAP=${bootstrap}
    export NIX9_LAB_NIX_STORE=${pkgs.nix}/bin/nix-store
    exec ${python}/bin/python ${source}/lab.py "$@"
  '';
}
