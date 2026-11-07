{
  pkgs ? import <nix9>,
}:
pkgs.clone.overrideAttrs (old: {
  name = "clone-workspace-${builtins.baseNameOf ./.}";
  src = ./source;
  patches = [ ];
  postInstall = old.postInstall + ''
    mkdir -p $out/nix-support
    echo `{cat /dev/sysname} > $out/nix-support/builder
    echo `{cat /dev/user} > $out/nix-support/identity
  '';
})
