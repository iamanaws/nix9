{
  mkDerivation,
  src,
  libbio,
}:
mkDerivation {
  name = "libmach";
  inherit src;
  sourceRoot = "source/sys/src/libmach";
  buildInputs = [ libbio ];
  postUnpack = ''
    for(file in *.c) {
      sed 's|"[^"]*/([^/]+/include/ureg.h)"|"${src}/\1"|' $file > converted.c
      mv converted.c $file
    }
    sed 's|: /sys/src/cmd/|: ${src}/sys/src/cmd/|' mkfile > converted.mk
    mv converted.mk mkfile
  '';
  makeFlags = [
    "LIB=libmach.a"
    "CFLAGS=-FTVw -I${src} -I${src}/sys/src/cmd"
  ];
  installPhase = ''
    mkdir -p $out/lib
    cp libmach.a $out/lib/
  '';
  meta.description = "Plan 9 executable and object file library";
}
