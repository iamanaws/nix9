derivation {
  name = "recovery";
  system = "x86_64-plan9";
  builder = "/bin/rc";
  args = [
    "-e"
    "-c"
    ''
      /bin/echo partial > $out
      /bin/echo ready > /tmp/nix9-recovery-ready
      while(! /bin/test -e /tmp/nix9-recovery-release) /bin/sleep 1
      /bin/echo complete > $out
    ''
  ];
}
