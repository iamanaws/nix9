{
  pkgs,
  python,
  testSupport,
  vm,
}:
pkgs.runCommand "native-image-tools" { requiredSystemFeatures = [ "kvm" ]; } ''
  ${python}/bin/python ${
    testSupport [
      ../../tests/export_tree.py
      ../../tests/artifacts.py
    ]
  }/export_tree.py \
    ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
    "$TMPDIR/tools.tar" amd64/bin/webfs amd64/bin/mpc \
    amd64/mkfile sys/src/mkfile.proto sys/src/cmd/mkone sys/src/cmd/mklib sys/src/cmd/mkmany sys/src/cmd/mksyslib rc/lib/rcmain
  mkdir -p "$out"
  tar -xf "$TMPDIR/tools.tar" -C "$out"
''
