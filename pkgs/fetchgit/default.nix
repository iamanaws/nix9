{ mkDerivation, git }:
{
  url,
  rev,
  hash,
  name ? "source",
}:
assert builtins.match "[0-9a-f]{40}" rev != null;
assert builtins.match "(git|https?)://.+" url != null;
mkDerivation {
  inherit name url rev;
  nativeBuildInputs = [ git ];
  outputHash = hash;
  outputHashAlgo = "";
  outputHashMode = "recursive";
  buildCommand = ''
    mkdir -p .git/objects/pack .git/refs/heads
    $tools/bin/webfs -m /mnt/web -T 60000
    git/get $url
    git/export-tree $rev $out
  '';
}
