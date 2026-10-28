{ pkgs }:
let
  upstream = import ./source.nix;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "go-plan9-bootstrap";
  inherit (upstream) version;
  src = pkgs.fetchurl upstream.src;
  nativeBuildInputs = [ pkgs.go ];
  dontConfigure = true;
  dontFixup = true;
  postPatch = ''
    patchShebangs src/*.bash
  '';
  buildPhase = ''
    runHook preBuild
    export GOROOT_BOOTSTRAP=${pkgs.go}/share/go
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache"
    export GOOS=plan9 GOARCH=amd64 CGO_ENABLED=0
    export GOENV=off GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local
    export GOMAXPROCS=2 GOFLAGS=-p=2
    cd src
    bash bootstrap.bash
    cd ../..
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out"
    tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
      -C go-plan9-amd64-bootstrap -cf - \
      bin pkg src lib misc api doc go.env VERSION LICENSE PATENTS \
      | gzip -n > "$out/go-bootstrap.tar.gz"
    runHook postInstall
  '';
  meta.description = "Cross-built Go seed for native 9front toolchain builds";
}
