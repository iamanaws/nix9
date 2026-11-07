{
  pkgs,
  nativePackageSet,
  testSupport,
}:
pkgs.runCommand "store-service-tests" { nativeBuildInputs = [ pkgs.nix ]; } ''
  mkdir "$out"
  export NIX_STATE_DIR="$TMPDIR/nix-state" NIX_LOG_DIR="$TMPDIR/nix-log"
  NIX_PATH=nix9=${nativePackageSet} nix-instantiate --store dummy:// --eval --strict --json \
    ${
      testSupport [
        ./store-service.nix
        ./store-service-checks.nix
        ./configuration-wait.c
      ]
    }/store-service-checks.nix > "$out/results.json"
''
