{ packages }:
let
  inherit (import packages) mkDerivation callPackage;
  dependency = mkDerivation {
    name = "override-dependency";
    buildCommand = ''
      mkdir -p $out/include
      echo dependency > $out/include/override.h
    '';
  };
  recipe =
    {
      mkDerivation,
      version ? "1",
      message ? "original",
    }:
    mkDerivation {
      pname = "override-example";
      inherit version;
      src = builtins.toFile "message" "${message}\n";
      unpackPhase = "";
      sourceRoot = ".";
      buildPhase = "cp $src message";
      installPhase = ''
        mkdir -p $out
        cp message $out/message
      '';
      postInstall = "echo original >> $out/hooks";
    };
  original = callPackage recipe { };
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
  called = callPackage recipe {
    version = "5";
    message = "called";
  };
  injection =
    assert callPackage ({ mkDerivation }: mkDerivation) { mkDerivation = "explicit"; } == "explicit";
    assert
      callPackage ({ libsec, missing }@args: builtins.attrNames args) { missing = true; } == [
        "libsec"
        "missing"
      ];
    true;
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
