{
  runCommand,
  gcc,
  go,
  cTools,
  sysroot,
}:
runCommand "ape-cross"
  {
    nativeBuildInputs = [
      gcc
      go
      cTools
    ];
    ccroot = sysroot;
  }
  ''
    source ${../../lib/ape-build.sh}
    apeCompile ${./main.c} main.6
    apeLink ape-tests main.6
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
    go run ${../format.go} ape-tests
    install -Dm755 ape-tests "$out/bin/ape-tests"
  ''
