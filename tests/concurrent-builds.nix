let
  src = builtins.toFile "client-source" "concurrent native builds\n";
  build =
    name:
    derivation {
      inherit name src;
      system = "x86_64-plan9";
      builder = "/bin/rc";
      args = [
        "-e"
        "-c"
        ''
          /bin/echo ran >> /tmp/n9-clients-${name}.count
          /bin/echo ready > /tmp/n9-clients-${name}.ready
          while(! /bin/test -e /tmp/n9-clients-release) /bin/sleep 1
          /bin/cat $src > $out
        ''
      ];
    };
in
{
  a = build "client-a";
  b = build "client-b";
}
