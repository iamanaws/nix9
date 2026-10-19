{ packages }:
let
  inherit (import packages) mkDerivation callPackage;
  makeDependency =
    message:
    mkDerivation {
      name = "override-${message}";
      buildCommand = ''
        mkdir -p $out/include
        echo ${message} > $out/include/override.h
      '';
    };
  dependency = makeDependency "dependency";
  replacement = makeDependency "replacement";
  recipe =
    {
      mkDerivation,
      version ? "1",
      message ? "original",
      dependency ? null,
    }:
    mkDerivation {
      pname = "override-example";
      inherit version;
      src = builtins.toFile "message" "${message}\n";
      unpackPhase = "";
      sourceRoot = ".";
      buildInputs = if dependency == null then [ ] else [ dependency ];
      buildPhase = "cp $src message";
      installPhase = ''
        mkdir -p $out
        cp message $out/message
      '';
      postInstall =
        "echo original >> $out/hooks"
        + (
          if dependency == null then
            ""
          else
            ''

              cat /sys/include/override.h > $out/argument
            ''
        );
    };
  original = callPackage recipe { };
  called = callPackage recipe {
    version = "5";
    message = "called";
    inherit dependency;
  };
  arguments = called.override {
    version = "6";
    dependency = replacement;
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
  inherit
    original
    changed
    called
    arguments
    ;
  argumentChain = arguments.override (old: {
    version = "7";
    message = old.message + " chained";
  });
  mixed =
    (arguments.overrideAttrs (old: {
      version = "8";
      postInstall = old.postInstall + "\necho attrs >> $out/hooks";
    })).override
      { message = "mixed"; };
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
  unchanged =
    original.drvPath == (original.overrideAttrs (_: { })).drvPath
    && original.drvPath == (original.override { }).drvPath
    && original.drvPath == (original.override (_: { })).drvPath;
}
