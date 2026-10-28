{ mkDerivation }:
{
  name,
  file,
  hash,
}:
mkDerivation {
  inherit name;
  outputHash = hash;
  outputHashAlgo = "sha256";
  outputHashMode = "flat";
  buildCommand = ''
    cat '${builtins.replaceStrings [ "'" ] [ "''" ] file}' > $out
  '';
}
