{ packages }:
let
  inherit (import packages) stdenv;
  package = stdenv.mkDerivation {
    name = "mk-phases";
    src = builtins.toFile "mkfile" ''
      all:V:
        test $"COMMON '=' 'common value'
        test $STAGE '=' build
        echo built > built
      install:V:
        test $"COMMON '=' 'common value'
        test $STAGE '=' install
        cp built $BIN/message
    '';
    unpackPhase = "cp $src mkfile";
    sourceRoot = ".";
    makeFlags = [ "COMMON=common value" ];
    buildFlags = [ "STAGE=build" ];
    installFlags = [ "STAGE=install" ];
  };
in
{
  default = package;
  custom = package.overrideAttrs (_: {
    name = "mk-custom-file";
    makefile = "alternate.mk";
    unpackPhase = "cp $src alternate.mk";
  });
  override = package.overrideAttrs (_: {
    name = "mk-override";
    makefile = "missing.mk";
    buildPhase = "echo overridden > built";
    installPhase = "cp built $out";
  });
  noMkfile = stdenv.mkDerivation {
    name = "no-mkfile";
    postBuild = "echo hook > $out";
  };
  singleCommand = package.overrideAttrs (_: {
    name = "mk-single-command";
    makefile = "missing.mk";
    buildCommand = "echo single > $out";
  });
  failBuild = package.overrideAttrs (_: {
    buildFlags = [ "STAGE=wrong" ];
  });
  failInstall = package.overrideAttrs (_: {
    installFlags = [ "STAGE=wrong" ];
  });
}
