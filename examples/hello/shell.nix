{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.mkShell {
  name = "hello-shell";
  inputsFrom = [ (import ./default.nix { inherit pkgs; }) ];
  shellHook = "echo 'Build with: mk'";
}
