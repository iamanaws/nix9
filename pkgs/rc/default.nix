{
  stdenv,
  src,
  buildPackages,
}:
stdenv.mkDerivation {
  name = "rc";
  inherit src;
  nativeBuildInputs = [ buildPackages.yacc ];
}
