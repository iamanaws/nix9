{
  pkgs,
  python,
  testSupport,
  vm,
}:
name:
{
  script,
  files ? [ ],
  args,
  nativeBuildInputs ? [ ],
  env ? { },
  preRun ? "",
}:
pkgs.runCommand name
  (
    {
      requiredSystemFeatures = [ "kvm" ];
    }
    // pkgs.lib.optionalAttrs (nativeBuildInputs != [ ]) { inherit nativeBuildInputs; }
    // env
  )
  (
    preRun
    + ''
      ${python}/bin/python ${testSupport ([ script ] ++ files)}/${baseNameOf script} \
        ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 ${args}
    ''
  )
