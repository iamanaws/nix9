{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.mkShell {
  name = "hello-shell";
  shellHook = "echo 'Build with: 6c -o hello.6 hello.c; 6l -o hello hello.6'";
}
