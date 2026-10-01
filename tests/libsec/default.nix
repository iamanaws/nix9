{
  runCommand,
  cTools,
  sysroot,
  libc,
  libsec,
  libmp,
}:
runCommand "libsec-cross-tests"
  {
    nativeBuildInputs = [ cTools ];
    ccroot = sysroot;
  }
  ''
    mkdir -p "$out/bin" "$out/src"
    for test in sha2 hmac chacha aesgcm eg; do
      cp ${libsec.source}/sys/src/libsec/test/$test.c "$out/src/"
    done
    cp ${./mp.c} "$out/src/mp.c"
    for test in sha2 hmac chacha aesgcm eg mp; do
      6c -D_Noreturn= -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
        -I ${libsec.source}/sys/src/libmp/port -o "$test.6" "$out/src/$test.c"
      6l -H2 -L ${libc}/lib -L ${libsec}/lib -L ${libmp}/lib -o "$out/bin/$test" "$test.6"
    done
  ''
