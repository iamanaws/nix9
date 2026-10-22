{
  pkgs,
  python,
  testSupport,
  vm,
  nativeNix,
  nativePackageSet,
}:
let
  nativeBootstrapBuild =
    let
      revision = builtins.substring 0 12 (
        builtins.hashString "sha256" "${nativeNix} ${nativePackageSet} ${./native-bootstrap} ${../examples/hello} ${../examples/ramfs}"
      );
    in
    pkgs.runCommand "nix9-${revision}-bootstrap.tar"
      {
        requiredSystemFeatures = [ "kvm" ];
        nativeBuildInputs = [ pkgs.nix ];
      }
      ''
        ${python}/bin/python ${
          testSupport [
            ../tests/native_publish.py
            ../tests/cache_publish.py
            ../tests/artifacts.py
          ]
        }/native_publish.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
          ${nativeNix} ${nativePackageSet} ${./native-bootstrap} ${../examples/hello} ${../examples/ramfs} \
          /usr/local/pkg/nix9-${revision} "$out"
      '';
in
# The archive is self-contained; embedded host debug paths need no GC roots.
pkgs.runCommand "nix9-bootstrap.tar"
  {
    __structuredAttrs = true;
    unsafeDiscardReferences.out = true;
  }
  ''
    cp ${nativeBootstrapBuild} "$out"
  ''
