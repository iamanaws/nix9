{ packages }:
let
  pkgs = import packages;
in
{
  badArchive = (pkgs.callPackage (packages + "/pkgs/go/archive.nix") { }) {
    name = "bad-go-archive.tar.gz";
    file = toString ./go/main.go;
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };
  program = pkgs.buildGoModule {
    pname = "nix9-go-check";
    version = "1";
    src = ./go;
    vendor = ./go-vendor;
  };
  missingVendor = pkgs.buildGoModule {
    pname = "nix9-go-missing-vendor";
    version = "1";
    src = ./go;
    doCheck = false;
  };
  shell = pkgs.mkShell {
    nativeBuildInputs = [ pkgs.go ];
    shellHook = builtins.readFile (packages + "/pkgs/go/environment.rc");
  };
  standard = pkgs.mkDerivation {
    name = "go-standard-tests";
    nativeBuildInputs = [ pkgs.go ];
    buildCommand = builtins.readFile (packages + "/pkgs/go/environment.rc") + ''
      if(go test -short -p 2 -timeout 5m bytes compress/gzip crypto/sha256 encoding/json path/filepath sync unicode/utf8 > $out) {
        echo 'Go standard tests passed'
      }
      if not {
        cat $out
        exit 'Go standard tests failed'
      }
    '';
  };
  seedProgram =
    (pkgs.callPackage (packages + "/build-go-module.nix") {
      go = pkgs.goBootstrap;
      goEnvironment = builtins.readFile (packages + "/pkgs/go/environment.rc");
    })
      {
        pname = "nix9-go-seed-check";
        version = "1";
        src = ./go;
        vendor = ./go-vendor;
      };
}
