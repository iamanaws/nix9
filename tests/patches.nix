{ packages }:
let
  pkgs = import packages;
  change =
    path: before: after:
    builtins.toFile "message.patch" ''
      --- ${path}
      +++ ${path}
      @@ -1 +1 @@
      -${before}
      +${after}
    '';
  first = change "a/message" "original" "middle";
  second = change "a/message" "middle" "patched";
  package = pkgs.stdenv.mkDerivation {
    name = "patch-tests";
    src = builtins.toFile "message" "original\n";
    sourceRoot = ".";
    unpackPhase = ''
      cp $src message
      chmod u+w message
    '';
    patches = [
      first
      second
    ];
    prePatch = "echo prePatch > order";
    postPatch = "echo postPatch >> order";
    buildPhase = ''
      test `{cat $src} '=' original
      echo build >> order
    '';
    installPhase = ''
      echo install >> order
      mkdir -p $out
      cp message order $out/
    '';
  };
in
{
  default = package;
  empty = package.overrideAttrs { patches = [ ]; };
  flags = package.overrideAttrs {
    patches = [ (change "message" "original" "patched") ];
    patchFlags = [ "-p0" ];
  };
  override = package.overrideAttrs {
    patchPhase = "echo custom > message";
  };
  skipped = package.overrideAttrs {
    phases = [
      "unpackPhase"
      "buildPhase"
      "installPhase"
    ];
  };
  rejected = package.overrideAttrs {
    patches = [ (change "a/message" "wrong" "patched") ];
  };
  preFailure = package.overrideAttrs {
    prePatch = "echo pre-patch-failed; test -e /missing-patch-hook";
  };
  postFailure = package.overrideAttrs {
    postPatch = "echo post-patch-failed; test -e /missing-patch-hook";
  };
}
