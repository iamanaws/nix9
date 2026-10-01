{
  runCommand,
  cTools,
  sysroot,
  libc,
}:
runCommand "c-abi-cross"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    mkdir "$out"
    for unit in main callee; do
      6c -D_Noreturn= \
        -I ${sysroot}/amd64/include -I ${sysroot}/sys/include -I ${./.} \
        -o "$out/$unit.6" ${./.}/"$unit.c"
    done
    6l -H2 -L ${libc}/lib -o "$out/abi-tests" "$out/main.6" "$out/callee.6"
  ''
