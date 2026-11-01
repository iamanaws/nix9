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
    if(! test -r '${builtins.replaceStrings [ "'" ] [ "''" ] file}') {
      echo 'Go source builds need the native-go-bootstrap archive.' >[1=2]
      exit 'missing Go archive'
    }
    cat '${builtins.replaceStrings [ "'" ] [ "''" ] file}' > $out
  '';
}
