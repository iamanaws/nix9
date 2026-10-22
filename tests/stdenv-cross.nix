{ pkgs, stdenv }:
let
  generator = pkgs.runCommand "build-generator" { } ''
    mkdir -p "$out/bin" "$out/include"
    cat > "$out/bin/generate" <<'EOF'
    #!${pkgs.runtimeShell}
    echo '#define GENERATED_ANSWER 42'
    EOF
    chmod +x "$out/bin/generate"
    echo '#error build tool headers must not be used' > "$out/include/answer.h"
  '';
  library = stdenv.mkDerivation {
    name = "cross-answer-library";
    src = builtins.toFile "answer.c" "int answer(void) { return 42; }\n";
    buildCommand = ''
      mkdir -p $out/lib $out/include $out/bin
      $CC -o answer.6 $src
      $AR rc $out/lib/libanswer.a answer.6
      echo '#pragma lib "libanswer.a"
      int answer(void);
      ' > $out/include/answer.h
      cp $src $out/bin/target-only
      chmod +x $out/bin/target-only
    '';
  };
  libraries = stdenv.mkDerivation {
    name = "cross-libraries";
    propagatedBuildInputs = [ library ];
    buildCommand = "mkdir -p $out";
  };
  tools = stdenv.mkDerivation {
    name = "cross-generators";
    propagatedNativeBuildInputs = [ generator ];
    buildCommand = "mkdir -p $out";
  };
in
stdenv.mkDerivation {
  name = "cross-stdenv-tests";
  src = ./stdenv-cross;
  nativeBuildInputs = [ tools ];
  buildInputs = [ libraries ];
  preBuild = ''
    if(whatis target-only > /dev/null >[2]/dev/null) exit 'target command leaked into PATH'
  '';
  doCheck = true;
  checkPhase = "exit 'cross builds must not execute target checks'";
}
