{ mkDerivation, src }:
let
  upstream = import ./source.nix;
in
mkDerivation {
  pname = "go-bootstrap";
  inherit (upstream) version;
  inherit src;
  buildCommand = ''
    mkdir -p $out
    gunzip -c $src | @{ cd $out; tar x }
    test -s $out/bin/go
    test -s $out/pkg/tool/plan9_amd64/compile
  '';
}
