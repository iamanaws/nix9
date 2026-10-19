{ packages }:
let
  inherit (import packages) mkDerivation;
  dependency = mkDerivation {
    name = "override-dependency";
    buildCommand = ''
      mkdir -p $out/include
      echo dependency > $out/include/override.h
    '';
  };
  original = mkDerivation {
    pname = "override-example";
    version = "1";
    src = builtins.toFile "message" "original\n";
    unpackPhase = "";
    sourceRoot = ".";
    buildPhase = "cp $src message";
    installPhase = ''
      mkdir -p $out
      cp message $out/message
    '';
    postInstall = "echo original >> $out/hooks";
  };
  changed = original.overrideAttrs (old: {
    version = "2";
    src = builtins.toFile "message" "changed\n";
    buildInputs = (old.buildInputs or [ ]) ++ [ dependency ];
    postInstall = old.postInstall + ''

      test -s /sys/include/override.h
      echo ${dependency} > $out/dependency
      echo changed >> $out/hooks
    '';
  });
in
{
  inherit original changed;
  chained = changed.overrideAttrs (old: {
    version = "3";
    postInstall = old.postInstall + "\necho chained >> $out/hooks";
  });
  direct = original.overrideAttrs {
    version = "4";
    src = builtins.toFile "message" "direct\n";
  };
  unchanged = original.drvPath == (original.overrideAttrs (_: { })).drvPath;
}
