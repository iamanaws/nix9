{
  mkDerivation,
  src ? ./main.c,
}:
mkDerivation {
  name = "hello-c";
  inherit src;
  buildCommand = ''
    $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o hello.6 $src
    $tools/bin/mkdir -p $out/bin
    $tools/bin/6l -l -E _main -o $out/bin/hello-c hello.6 $tools/amd64/lib/libc.a
  '';
}
