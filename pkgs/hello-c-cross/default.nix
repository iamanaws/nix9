{
  runCommand,
  cTools,
  sysroot,
  go,
}:
runCommand "hello-c-cross-9front-amd64"
  {
    nativeBuildInputs = [
      cTools
      go
    ];
    ccroot = sysroot;
  }
  ''
    # goken9cc predates the _Noreturn annotation used by current 9front headers.
    6c -D_Noreturn= \
      -I ${sysroot}/amd64/include -I ${sysroot}/sys/include \
      -o hello.6 ${../hello-c-native/main.c}
    # Force Plan 9 a.out rather than the Linux host's default ELF format.
    6l -H2 -o hello-c hello.6
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
    go run ${../../tests/format.go} hello-c
    install -Dm755 hello-c "$out/bin/hello-c"
  ''
