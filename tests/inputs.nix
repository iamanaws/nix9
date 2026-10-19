{ packages }:
let
  inherit (import packages) mkDerivation mkShell;
  generator = mkDerivation {
    name = "native-generator";
    src = builtins.toFile "generate.c" ''
      #include <u.h>
      #include <libc.h>
      void main(void) { print("#define BUILD_NUMBER 42\n"); exits(nil); }
    '';
    buildCommand = ''
      mkdir -p $out/bin $out/include
      6c -o generate.6 $src
      6l -s -o $out/bin/generate generate.6
      echo tool-only > $out/include/build-tool-only.h
    '';
  };
  generators = [
    generator
    (generator.overrideAttrs (_: {
      name = "other-generator";
      src = builtins.toFile "generate.c" ''
        #include <u.h>
        #include <libc.h>
        void main(void) { print("#define BUILD_NUMBER 99\n"); exits(nil); }
      '';
    }))
  ];
  library =
    ape:
    let
      suffix = if ape then "/ape" else "";
      answer = if ape then "24" else "42";
    in
    mkDerivation {
      name = if ape then "ape-answer" else "native-answer";
      src = builtins.toFile "answer.c" "int answer(void) { return ${answer}; }\n";
      header = builtins.toFile "answer.h" ''
        ${if ape then "" else "#pragma lib \"/amd64/lib/libanswer.a\""}
        #define EXPECTED_ANSWER ${answer}
        int answer(void);
      '';
      buildCommand = ''
        objtype=amd64
        ${if ape then "pcc -c" else "6c"} -o answer.6 $src
        mkdir -p $out/include${suffix} $out/lib${suffix} $out/bin
        cp $header $out/include${suffix}/answer.h
        ar rc $out/lib${suffix}/libanswer.a answer.6
        cp $tools/bin/echo $out/bin/input-only
      '';
    };
  libraries = [
    (library false)
    (library true)
  ];
  program =
    ape:
    mkDerivation {
      name = if ape then "ape-inputs" else "native-inputs";
      nativeBuildInputs = generators;
      buildInputs = libraries;
      unpackPhase = "";
      sourceRoot = ".";
      src = builtins.toFile "main.c" (
        if ape then
          ''
            #define _POSIX_SOURCE
            #include <stdio.h>
            #include <stdlib.h>
            #include <string.h>
            #include <unistd.h>
            #include <answer.h>
            #include "generated.h"
            int main(int argc, char **argv) {
              if (argc > 1) {
                char *path = getenv("PATH");
                char *args[] = { "generate", NULL };
                if (path == NULL || strstr(path, "native-generator/bin") == NULL) {
                  fprintf(stderr, "unexpected PATH: %s\n", path == NULL ? "(null)" : path);
                  return 1;
                }
                execvp(args[0], args);
                perror("execvp generate");
                return 1;
              }
              if (EXPECTED_ANSWER != 24 || answer() != 24 || BUILD_NUMBER != 42) return 1;
              puts("ape inputs PASS");
              return 0;
            }
          ''
        else
          ''
            #include <u.h>
            #include <libc.h>
            #include <answer.h>
            #include "generated.h"
            void main(void) {
              if (EXPECTED_ANSWER != 42 || answer() != 42 || BUILD_NUMBER != 42) exits("wrong answer");
              print("native inputs PASS\n");
              exits(nil);
            }
          ''
      );
      buildPhase = ''
        test ! -e /sys/include/build-tool-only.h
        if(input-only) exit 'buildInputs command leaked into path'
        generate > generated.h
        objtype=amd64
        ${if ape then "pcc -c" else "6c"} -I . -o main.6 $src
        ${if ape then "pcc -o answer main.6 -lanswer" else "6l -s -o answer main.6"}
      '';
      doCheck = true;
      checkPhase = ''
        ./answer
        ${
          if ape then
            ''
              ./answer tool > generated-from-ape.h
              test -s generated-from-ape.h
              awk '$0 != "#define BUILD_NUMBER 42" { exit 1 }' generated-from-ape.h
            ''
          else
            ""
        }
      '';
      installPhase = ''
        mkdir -p $out/bin
        cp answer $out/bin/answer
      '';
    };
  shellNative = (program false).overrideAttrs (_: {
    nativeBuildInputs = [ (builtins.elemAt generators 1) ];
    buildCommand = "exit 'inputsFrom package must not be built'";
    shellHook = "NIX9_SHELL_HOOK=$NIX9_SHELL_HOOK^native";
  });
  shellApe = (program true).overrideAttrs (old: {
    buildInputs = [ shellNative ] ++ old.buildInputs;
    buildCommand = "exit 'inputsFrom package must not be built'";
    shellHook = "NIX9_SHELL_HOOK=ape";
  });
in
{
  native = program false;
  ape = program true;
  shell = mkShell {
    name = "input-shell";
    inputsFrom = [
      shellNative
      shellApe
    ];
    nativeBuildInputs = [ generator ];
    shellHook = ''
      NIX9_SHELL_HOOK=$NIX9_SHELL_HOOK^shell
      shellSource=${(program false).src}
      apeShellSource=${(program true).src}
      NIX9_SHELL_TEST=ready
      echo NIX9-SHELL-READY
    '';
  };
  failedShell = mkShell {
    name = "failed-shell";
    shellHook = "test -e /no-such-shell-hook-fixture";
  };
}
