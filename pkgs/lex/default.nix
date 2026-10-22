{
  stdenv,
  src,
  libbio,
  buildPackages,
}:
stdenv.mkDerivation {
  name = "lex";
  inherit src;
  nativeBuildInputs = [ buildPackages.yacc ];
  buildInputs = [ libbio ];
  postInstall = ''
    mkdir -p $out/libexec $out/share/lex
    mv $out/bin/lex $out/libexec/lex
    echo '#ifdef __STDC__
    #pragma lib "/$M/lib/ape/libl.a"
    #else
    #pragma lib "libl.a"
    #endif' > $out/share/lex/ncform
    sed '1d' ncform >> $out/share/lex/ncform
    echo '#!/bin/rc
    rfork n || exit $status
    bind '^$out^'/share/lex /sys/lib/lex || exit $status
    exec '^$out^'/libexec/lex $*
    ' > $out/bin/lex
    chmod +x $out/bin/lex
  '';
  meta.description = "Plan 9 lexical analyzer generator";
}
