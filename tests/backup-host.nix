{
  pkgs,
  nativePackageSet,
  testSupport,
}:
pkgs.runCommand "backup-tests" { nativeBuildInputs = [ pkgs.nix ]; } ''
  mkdir "$out"
  export NIX_STATE_DIR="$TMPDIR/nix-state" NIX_LOG_DIR="$TMPDIR/nix-log"
  NIX_PATH=nix9=${nativePackageSet} nix-instantiate --store dummy:// --eval --strict --json \
    ${
      testSupport [
        ./backups.nix
        ./backup-checks.nix
      ]
    }/backup-checks.nix > "$out/results.json"
''
