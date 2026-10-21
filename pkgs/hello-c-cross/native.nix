{
  mkDerivation,
  src ? ./main.c,
}:
mkDerivation {
  name = "hello-c";
  inherit src;
  buildCommand = ''
    6c -I $tools/sys/include -I $tools/amd64/include -o hello.6 $src
    $tools/bin/mkdir -p $out/bin
    6l -l -E _main -o $out/bin/hello-c hello.6 $tools/bootstrap/lib/libc.a
  '';
}
