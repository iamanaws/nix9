{
  pkgs,
  nativePackageSet,
  testSupport,
}:
pkgs.runCommand "netroot-tests" { nativeBuildInputs = [ pkgs.nix ]; } ''
  mkdir "$out"
  export NIX_STATE_DIR="$TMPDIR/nix-state" NIX_LOG_DIR="$TMPDIR/nix-log"
  NIX_PATH=nix9=${nativePackageSet} nix-instantiate --store dummy:// --eval --strict --json \
    ${
      testSupport [
        ./netroot.nix
        ./netroot-checks.nix
      ]
    }/netroot-checks.nix > "$out/results.json"
''
