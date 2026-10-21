let
  release = import /usr/local/pkg/nix9/release.nix;
in
release.overrideAttrs (old: {
  name = "nix9-upgrade-test";
  installPhase = old.installPhase + ''
    chmod u+w $out/packages $out/packages/default.nix
    cp $out/packages/default.nix $out/packages/base.nix
    echo 'import ./base.nix // { releaseTest = "two"; }' > $out/packages/default.nix
  '';
})
