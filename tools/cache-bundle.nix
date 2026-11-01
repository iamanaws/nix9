# nix build --impure --file tools/cache-bundle.nix -o result-cache-publication
let
  flake = builtins.getFlake (toString ../.);
  pkgs = import flake.inputs.nixpkgs { system = "x86_64-linux"; };
  project = import ../pkgs {
    inherit pkgs;
    inherit (flake.inputs) ninefront goken9cc;
  };
  selected = builtins.filter (name: name != "go") (import ../pkgs/cache-packages.nix);
  farm =
    name: entries:
    pkgs.linkFarm name (pkgs.lib.mapAttrsToList (name: path: { inherit name path; }) entries);
in
farm "nix9-cache" {
  native-bootstrap = project.nativeBootstrap;
  cross-packages = farm "nix9-cross-packages" (
    builtins.listToAttrs (
      map (name: {
        inherit name;
        value = project.${name};
      }) selected
    )
  );
  cross-toolchain = farm "nix9-cross-toolchain" (
    project.sources
    // {
      cc = project.stdenv.cc;
      tools = project.stdenv.tools;
      inherit (project) libc libap libbsd;
    }
  );
}
