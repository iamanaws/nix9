{
  pkgs,
  python,
  testSupport,
  vm,
}:
pkgs.runCommand "9front-11952-netroot-base" { requiredSystemFeatures = [ "kvm" ]; } ''
  export PYTHONPATH=${testSupport [ ../../tests/artifacts.py ]}
  ${python}/bin/python ${./extract.py} \
    ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 ${./root.proto} "$out"
''
