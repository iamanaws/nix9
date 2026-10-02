# Bootstrap tools are an explicit store input.
{
  src ? ./main.c,
  tools,
}:
derivation {
  name = "hello-c";
  system = "x86_64-plan9";
  inherit src tools;
  builder = "/bin/rc";
  args = [
    "-e"
    "-c"
    ''
      $tools/bin/6c -I $tools/sys/include -I $tools/amd64/include -o hello.6 $src
      /bin/mkdir -p $out/bin
      $tools/bin/6l -l -E _main -o $out/bin/hello-c hello.6 $tools/amd64/lib/libc.a
    ''
  ];
}
