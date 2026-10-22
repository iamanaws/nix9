{ packages }:
let
  pkgs = import packages;
  rebuilt = pkgs.cc.override {
    inherit (pkgs)
      stdenv
      libc
      libbio
      yacc
      ;
  };
  program = pkgs.stdenv.mkDerivation {
    name = "cc-tests";
    compiler = pkgs.cc;
    inherit (pkgs) libc;
    nativeBuildInputs = [ pkgs.sha1sum ];
    src = ./libc.c;
    assembly = builtins.toFile "answer.s" ''
      TEXT answer(SB), 1, $0
      MOVL $42, AX
      RET
    '';
    main = builtins.toFile "main.c" ''
      #include <u.h>
      #include <libc.h>
      int answer(void);
      void main(void) {
        assert(answer() == 42);
        print("native cc PASS\n");
        exits(nil);
      }
    '';
    ape = builtins.toFile "ape.c" ''
      #include <stdio.h>
      #if ANSWER != 42
      #error missing preprocessor definition
      #endif
      int main(void) { puts("APE cc PASS"); return 0; }
    '';
    buildCommand = ''
      for(command in 6a 6c 6l cpp pcc) {
        test `{whatis $command} '=' $compiler/bin/$command
        test ! -e $tools/bin/$command
      }
      test `{sha1sum < /amd64/lib/libc.a} '=' `{sha1sum < $libc/lib/libc.a}
      echo '#!/bin/rc
      exit bootstrap-compiler-unavailable' > blocked
      chmod +x blocked
      for(command in 6a 6c 6l cpp pcc) bind blocked $tools/bootstrap/bin/$command
      mkdir -p $out/bin
      cp $assembly answer.s
      cp $main main.c
      6a -o answer.6 answer.s
      6c -o main.6 main.c
      6l -o $out/bin/answer main.6 answer.6
      $out/bin/answer
      cp $src libc.c
      6c -o libc.6 libc.c
      6l -o $out/bin/libc-test libc.6
      $out/bin/libc-test
      cp $ape ape.c
      pcc -E '-DANSWER=42' ape.c > preprocessed.c
      test -s preprocessed.c
      pcc -P '-DANSWER=42' ape.c
      test -s ape.i
      pcc -c '-DANSWER=42' -o ape.6 ape.c
      pcc -o $out/bin/ape ape.6
      $out/bin/ape
      echo invalid-c-source > invalid.c
      if(6c invalid.c) exit 'compiler accepted invalid C'
      if(pcc -c invalid.c) exit 'compiler driver accepted invalid C'
      echo passed > $out/checked
    '';
  };
in
{
  compiler = pkgs.cc;
  inherit rebuilt program;
  rebuiltProgram = program.overrideAttrs {
    name = "rebuilt-cc-tests";
    compiler = rebuilt;
    nativeBuildInputs = [
      rebuilt
      pkgs.sha1sum
    ];
  };
  shell = pkgs.mkShell { };
}
