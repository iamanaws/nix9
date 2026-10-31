{
  pkgs ? import <nix9>,
}:
pkgs.mkDerivation {
  name = "netroot-project";
  src = builtins.toFile "hello.c" ''
    #include <u.h>
    #include <libc.h>
    void main(void) { print("hello from a network-root CPU\n"); exits(nil); }
  '';
  buildCommand = ''
    mkdir -p $out/bin
    6c -o hello.6 $src
    6l -o $out/bin/hello hello.6
    cat /dev/sysname > $out/compiled-on
  '';
}
