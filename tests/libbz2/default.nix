{
  runCommand,
  gcc,
  go,
  cTools,
  sysroot,
  libbz2,
  libap,
  libbsd,
}:
runCommand "libbz2-consumer"
  {
    nativeBuildInputs = [
      gcc
      go
      cTools
    ];
    ccroot = sysroot;
    apeCoreLibrary = "${libap}/lib/libap.a";
    apeBsdLibrary = "${libbsd}/lib/libbsd.a";
  }
  ''
    source ${../../lib/ape-build.sh}
    apeCompile ${./main.c} main.6 c99 -I ${libbz2}/include
    apeLink bz2-test main.6 ${libbz2}/lib/libbz2.a
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
    go run ${../format.go} bz2-test
    install -Dm755 bz2-test "$out/bin/bz2-test"
    install -Dm644 main.6 "$out/main.6"
  ''
