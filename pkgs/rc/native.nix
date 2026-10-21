{
  stdenv,
  src,
  yacc,
}:
stdenv.mkDerivation {
  name = "rc";
  inherit src;
  nativeBuildInputs = [ yacc ];
}
