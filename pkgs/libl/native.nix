{
  stdenv,
  src,
  header,
}:
stdenv.mkDerivation {
  name = "libl";
  inherit src header;
  buildPhase = ''
    cp $header libl.h
    for(source in *.c) pcc -c -D_RESEARCH_SOURCE -I . $source
  '';
  installPhase = ''
    mkdir -p $out/lib/ape $out/include/ape
    ar rc $out/lib/ape/libl.a *.6
    cp libl.h $out/include/ape/
  '';
  meta.description = "APE scanner runtime for lex";
}
