{
  mkDerivation,
  src ? ./main.c,
}:
mkDerivation {
  name = "hello-c";
  inherit src;
  buildCommand = ''
    6c -o hello.6 $src
    $tools/bin/mkdir -p $out/bin
    6l -o $out/bin/hello-c hello.6
  '';
}
