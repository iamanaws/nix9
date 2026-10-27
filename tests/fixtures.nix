{
  pkgs,
  secSource,
  sha1sum,
  mpc,
  callPackage,
}:
rec {
  compressedText = pkgs.runCommand "build-tools-input.gz" { nativeBuildInputs = [ pkgs.gzip ]; } ''
    printf 'hello\n' | gzip -n > "$out"
  '';
  nixProbe = callPackage ./libutil { };
  nativePackages = pkgs.runCommand "native-package-inputs" { } ''
    mkdir "$out"
    cp -r ${secSource} "$out/libsec"
    cp ${../pkgs/libsec/default.nix} "$out/libsec.nix"
    cp -r ${mpc} "$out/mpc"
    cp ${../pkgs/sha1sum/default.nix} "$out/sha1sum.nix"
    cp ${../lib/mk-derivation.nix} "$out/mk-derivation.nix"
    cp ${../lib/setup-environment.nix} "$out/setup-environment.nix"
    cp ${../lib/collect-inputs.nix} "$out/collect-inputs.nix"
    cp ${sha1sum.source} "$out/sha1sum.c"
    cp ${sha1sum}/bin/sha1sum "$out/cross"
  '';
  abiCross = callPackage ./c-abi { };
  apeCross = callPackage ./ape { };
  secCross = callPackage ./libsec { };
  stdenvCross = callPackage ./stdenv-cross.nix { inherit pkgs; };
  crossShellPrograms = callPackage ./cross-shell.nix { inherit pkgs stdenvCross; };
  cloneRepository = pkgs.fetchgit (
    import ../pkgs/clone/source.nix
    // {
      leaveDotGit = true;
      deepClone = true;
      hash = "sha256-xPcmrMzO5TpMo3iqQRhuJlomxzLDW4gB8hjhMuEDfJI=";
    }
  );
  libbz2Consumer = callPackage ./libbz2 { };
}
