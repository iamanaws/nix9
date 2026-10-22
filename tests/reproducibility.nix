{ packages }:
let
  pkgs = import packages;
in
{
  rebuilt = {
    buildTools = pkgs.buildTools.override {
      inherit (pkgs)
        stdenv
        yacc
        libbio
        libregexp
        ;
    };
    cc = pkgs.cc.override { inherit (pkgs) stdenv; };
    libc = pkgs.libc.override { inherit (pkgs) stdenv; };
    rc = pkgs.rc.override { inherit (pkgs) stdenv yacc; };
    yacc = pkgs.yacc.override { inherit (pkgs) stdenv; };
    patch = pkgs.patch.override { inherit (pkgs.stdenv) mkDerivation; };
    ar = pkgs.ar.override {
      inherit (pkgs.stdenv) mkDerivation;
      inherit (pkgs) patch;
    };
    libbio = pkgs.libbio.override { inherit (pkgs.stdenv) mkDerivation; };
    libstdio = pkgs.libstdio.override { inherit (pkgs.stdenv) mkDerivation; };
    libmach = pkgs.libmach.override { inherit (pkgs.stdenv) mkDerivation; };
    libregexp = pkgs.libregexp.override { inherit (pkgs.stdenv) mkDerivation; };
    mk = pkgs.mk.override { inherit (pkgs.stdenv) mkDerivation; };
  };
  archives = pkgs.stdenv.mkDerivation {
    name = "ar-epoch-tests";
    src = builtins.toFile "fixture.c" "int answer(void) { return 42; }\n";
    main = builtins.toFile "main.c" ''
      #include <u.h>
      #include <libc.h>
      int answer(void);
      void main(void) {
        if(answer() != 42) sysfatal("wrong archive member");
        print("archive link PASS\n");
        exits(nil);
      }
    '';
    buildCommand = ''
      mkdir -p $out
      cp $src fixture.c
      6c -o fixture.6 fixture.c
      @{ SOURCE_DATE_EPOCH=0; ar rc $out/zero.a fixture.6 }
      @{ SOURCE_DATE_EPOCH=42; ar rc $out/custom.a fixture.6 }
      @{ rm /env/SOURCE_DATE_EPOCH; ar rc $out/ordinary.a fixture.6 }
      cp $main main.c
      6c -o main.6 main.c
      for(archive in zero custom ordinary) {
        6l -o $out/$archive main.6 $out/$archive.a
        $out/$archive
      }
    '';
  };
}
