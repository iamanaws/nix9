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
  preBuild = ''
    bind -b $src/sys/src/cmd /sys/src/cmd
    for(arch in 386 68020 amd64 arm arm64 mips power power64 sparc sparc64) {
      bind $src/$arch/include/ureg.h /$arch/include/ureg.h
    }
  '';
  makeFlags = [ "LIB=libmach.a" ];
  installPhase = ''
    mkdir -p $out/lib
    cp libmach.a $out/lib/
  '';
  meta.description = "Plan 9 executable and object file library";
}
