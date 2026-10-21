{ packages }:
let
  pkgs = import packages;
  program =
    inputs:
    pkgs.stdenv.mkDerivation {
      name = "declared-library";
      buildInputs = inputs;
      src = builtins.toFile "bio.c" ''
        #include <u.h>
        #include <libc.h>
        #include <bio.h>
        void main(void) {
          Biobuf out;
          Binit(&out, 1, OWRITE);
          Bprint(&out, "declared library PASS\n");
          Bterm(&out);
          exits(nil);
        }
      '';
      buildCommand = ''
        for(command in 6a 6c 6l ar mk rc) test ! -e $tools/bin/$command
        for(command in 6a 6c 6l) test `{whatis $command} '=' ${pkgs.cc}/bin/$command
        test `{whatis ar} '=' ${pkgs.ar}/bin/ar
        test `{whatis mk} '=' ${pkgs.mk}/bin/mk
        test `{whatis rc} '=' ${pkgs.rc}/bin/rc
        test ! -e /amd64/lib/libmach.a
        cp $src bio.c
        6c -o bio.6 bio.c
        mkdir -p $out/bin
        6l -o $out/bin/bio bio.6
      '';
    };
in
{
  declared = program [ pkgs.libbio ];
  undeclared = program [ ];
  ape = pkgs.stdenv.mkDerivation {
    name = "ape-runtime";
    src = builtins.toFile "ape.c" ''
      #include <stdio.h>
      int main(void) { puts("APE runtime PASS"); return 0; }
    '';
    buildCommand = ''
      cp $src ape.c
      pcc -o $out ape.c
    '';
  };
}
