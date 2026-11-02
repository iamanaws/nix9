{
  stdenv,
  src,
  libbio,
}:
stdenv.mkDerivation {
  name = "yacc";
  inherit src;
  buildInputs = [ libbio ];
  sourceRoot = "source/sys/src/cmd";
  buildPhase = ''
    6c yacc.c
    6l -s -o yacc yacc.6
  '';
  installPhase = ''
    mkdir -p $out/bin $out/libexec $out/share/yacc
    cp yacc $out/libexec/yacc
    cp ../../lib/yaccpar ../../lib/yaccpars $out/share/yacc/
    echo '#!/bin/rc
    rfork n || exit $status
    bind -b '^$out^'/share/yacc /sys/lib || exit $status
    exec '^$out^'/libexec/yacc $*
    ' > $out/bin/yacc
    chmod +x $out/bin/yacc
  '';
  meta.description = "Plan 9 parser generator";
}
