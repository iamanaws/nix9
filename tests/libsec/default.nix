{
  runCommand,
  cTools,
  sysroot,
  libc,
  libsec,
}:
runCommand "libsec-cross-tests"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    mkdir -p "$out/bin" "$out/src"
    for test in sha2 hmac chacha aesgcm; do
      cp ${libsec.source}/sys/src/libsec/test/$test.c "$out/src/"
      6c -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
        -I ${libsec.source}/sys/src/libmp/port -o "$test.6" "$out/src/$test.c"
      6l -H2 -L ${libc}/lib -L ${libsec}/lib -o "$out/bin/$test" "$test.6"
    done
  ''
