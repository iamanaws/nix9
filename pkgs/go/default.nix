{
  stdenv,
  goBootstrap,
  src,
}:
let
  upstream = import ./source.nix;
in
stdenv.mkDerivation {
  pname = "go";
  inherit (upstream) version;
  inherit src;
  sourceRoot = "go";
  unpackPhase = ''
    gunzip -c $src | tar x
  '';
  nativeBuildInputs = [ goBootstrap ];
  disallowedReferences = [ goBootstrap ];
  buildPhase = ''
    home=$TMPDIR
    HOME=$TMPDIR
    GOROOT_BOOTSTRAP=${goBootstrap}
    GOOS=plan9
    GOARCH=amd64
    GOHOSTOS=plan9
    GOHOSTARCH=amd64
    CGO_ENABLED=0
    GOENV=off
    GOPROXY=off
    GOSUMDB=off
    GOTOOLCHAIN=local
    GOTELEMETRY=off
    GOCACHE=$TMPDIR/go-cache
    GOPATH=$TMPDIR/go-path
    GOTMPDIR=$TMPDIR/go-tmp
    GOMAXPROCS=2
    GOFLAGS='-p=2'
    mkdir -p $GOCACHE $GOPATH $GOTMPDIR
    @{ cd src; rc -e ./make.rc }
  '';
  installPhase = ''
    mkdir -p $out
    tar cf /fd/1 bin pkg src lib misc api doc go.env VERSION LICENSE PATENTS | @{ cd $out; tar xf /fd/0 }
  '';
  meta.description = "Go toolchain built natively on 9front";
}
