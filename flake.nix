{
  description = "Experiments in Nix-managed cross compilation for 9front";

  nixConfig = {
    extra-substituters = [ "https://nix9.cachix.org" ];
    extra-trusted-public-keys = [
      "nix9.cachix.org-1:geiAfwmo+PftMUs4uIL9so9vuNAgP36d+CM9k86Q8nk="
    ];
  };

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    ninefront = {
      url = "github:majiru/9front-in-a-box";
      flake = false;
    };
    goken9cc = {
      url = "github:aryx/goken9cc/e549ce5515ac036ea757d1ebc660686e59ccc35b";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      ninefront,
      goken9cc,
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      project = import ./pkgs { inherit pkgs ninefront goken9cc; };
      tests = import ./tests {
        inherit pkgs;
        packages = project;
      };
    in
    {
      lib = {
        inherit (project) mkPlan9Program mkGuestPackage mkGuestEnvironment;
        inherit (project) stdenv callPackage mkShell;
        mkDerivation = import ./lib/mk-derivation.nix;
      };
      packages.${system} = project.flakePackages // tests.packages;
      apps.${system} =
        builtins.mapAttrs
          (_: package: {
            type = "app";
            meta.description = "9front experiment: ${package.meta.mainProgram}";
            program = "${package}/bin/${package.meta.mainProgram}";
          })
          {
            inherit (project.flakePackages) setup-vm run-vm;
            inherit (tests.packages) smoke-test smoke-test-c-cross;
          };
      checks.${system} = tests.checks;
      devShells.${system} = {
        default = pkgs.mkShell {
          packages = [
            pkgs.go
            pkgs.qemu
            project.python
            pkgs.nixfmt-tree
          ];
        };
        cross = project.mkShell {
          buildInputs = [
            project.libap
            project.libbsd
          ];
        };
      };
      formatter.${system} = pkgs.nixfmt-tree;
    };
}
