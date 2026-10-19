{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.mkShell {
  name = "hello-shell";
  shellHook = "echo 'Build with: mk'";
}
