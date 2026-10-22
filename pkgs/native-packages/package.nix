{
  lib,
  runCommand,
  nativeTools,
  sources,
  packageDefinitions,
}:
let
  copy = destination: source: ''cp -r ${source} "$out/${destination}"'';
  files = {
    "tools" = nativeTools;
    "default.nix" = ./default.nix;
    "bootstrap.nix" = ./bootstrap.nix;
    "pkgs/packages.nix" = ../packages.nix;
    "pkgs/fetchurl" = ../fetchurl;
    "pkgs/fetchgit" = ../fetchgit;
    "profile" = ../../lib/profile.rc;
    "bin/nix-profile" = ../../lib/nix-profile.rc;
  };
in
runCommand "native-packages" { } ''
  mkdir -p "$out/pkgs" "$out/bin" "$out/sources"
  ${lib.concatStringsSep "\n" (lib.mapAttrsToList copy files)}
  ${lib.concatStringsSep "\n" (
    lib.mapAttrsToList (name: copy "sources/${name}") (builtins.removeAttrs sources [ "sysroot" ])
  )}
  ${lib.concatMapStringsSep "\n" (
    definition: copy "pkgs/${builtins.baseNameOf definition.path}" definition.path
  ) (builtins.attrValues packageDefinitions)}
  ${lib.concatMapStringsSep "\n" (name: copy name (../../lib + "/${name}")) [
    "mk-derivation.nix"
    "call-package.nix"
    "stdenv.nix"
    "setup-environment.nix"
    "collect-inputs.nix"
    "mk-shell.nix"
    "build-env.nix"
  ]}
  chmod +x "$out/bin/nix-profile"
''
