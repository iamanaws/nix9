{
  mkDerivation,
  src,
  lib9p,
}:
mkDerivation {
  name = "ramfs";
  inherit src;
  buildInputs = [ lib9p ];
  buildCommand = ''
    cp $src ramfs.c
    6c -o ramfs.6 ramfs.c
    mkdir -p $out/bin
    6l -o $out/bin/ramfs ramfs.6
  '';
  meta.description = "Memory file system";
}
