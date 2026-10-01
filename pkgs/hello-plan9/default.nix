{
  lib,
  stdenvNoCC,
  go,
}:
stdenvNoCC.mkDerivation {
  pname = "hello-plan9-amd64";
  version = "0.1.0";
  src = ./main.go;
  dontUnpack = true;
  nativeBuildInputs = [ go ];
  # The derivation executes on Linux; only its output targets Plan 9.
  GOOS = "plan9";
  GOARCH = "amd64";
  CGO_ENABLED = "0";
  GO111MODULE = "off";
  GOPROXY = "off";
  GOTOOLCHAIN = "local";
  buildPhase = ''
    runHook preBuild
    export GOCACHE="$TMPDIR/go-cache"
    go build -trimpath -buildvcs=false -ldflags=-buildid= -o hello "$src"
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    install -Dm755 hello "$out/bin/hello"
    runHook postInstall
  '';
  # Host strip/patchelf tools do not understand Plan 9 a.out.
  dontFixup = true;
  meta = {
    description = "Cross-compiled Plan 9/amd64 smoke-test executable";
    platforms = lib.platforms.linux;
  };
}
