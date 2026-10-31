{
  lib,
  runCommand,
  nativeTools,
  moduleLibrary,
  sources,
  packageDefinitions,
  netrootBase,
  goBootstrap ? null,
  goSource ? null,
}:
assert (goBootstrap == null) == (goSource == null);
let
  copy = destination: source: ''cp -r ${source} "$out/${destination}"'';
  files = {
    "tools" = nativeTools;
    "nixpkgs-lib" = moduleLibrary;
    "default.nix" = ./default.nix;
    "bootstrap.nix" = ./bootstrap.nix;
    "pkgs/packages.nix" = ../packages.nix;
    "pkgs/fetchurl" = ../fetchurl;
    "pkgs/fetchgit" = ../fetchgit;
    "profile" = ../../lib/profile.rc;
    "bin/nix-profile" = ../../lib/nix-profile.rc;
    "bin/nix9-rebuild" = ../../lib/system/rebuild.rc;
    "bin/nix9-deploy" = ../../lib/installation/deploy.rc;
    "bin/nix9-session" = ../../lib/system/graphical.rc;
    "system" = ../../lib/system;
    "installation" = ../../lib/installation;
    "netroot-base" = netrootBase;
    "examples/installation" = ../../examples/installation;
    "examples/network-server" = ../../examples/network-server;
    "examples/storage" = ../../examples/storage;
    "examples/backup" = ../../examples/backup;
    "examples/builders" = ../../examples/builders;
    "examples/workstation" = ../../examples/workstation;
    "examples/netroot" = ../../examples/netroot;
  }
  // (lib.optionalAttrs (goBootstrap != null) {
    "go-bootstrap.tar.gz" = goBootstrap + "/go-bootstrap.tar.gz";
    "go-bootstrap.sha256" = runCommand "go-bootstrap.sha256" { } ''
      sha256sum ${goBootstrap}/go-bootstrap.tar.gz | cut -d ' ' -f1 > "$out"
    '';
    "sources/go.tar.gz" = goSource;
    "pkgs/go" = ../go;
    "build-go-module.nix" = ../../lib/build-go-module.nix;
  });
in
runCommand "native-packages" { } ''
  mkdir -p "$out/pkgs" "$out/bin" "$out/sources" "$out/examples"
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
  chmod +x "$out/bin/nix-profile" "$out/bin/nix9-rebuild" "$out/bin/nix9-deploy" "$out/bin/nix9-session"
''
