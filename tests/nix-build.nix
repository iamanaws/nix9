{
  message ? "hello",
}:
let
  mk =
    name: script: extra:
    derivation (
      {
        inherit name;
        system = "x86_64-plan9";
        builder = "/bin/rc";
        args = [
          "-c"
          script
        ];
      }
      // extra
    );
in
{
  hello = mk "cli-hello" "/bin/echo ran >> /tmp/nix9-cli-count; /bin/echo $message > $out" {
    inherit message;
  };
  other = mk "cli-other" "/bin/echo built > /tmp/nix9-cli-other; /bin/echo other > $out" { };
  multiple = mk "cli-multiple" "/bin/echo output > $out; /bin/echo headers > $dev" {
    outputs = [
      "out"
      "dev"
    ];
  };
  failed = mk "cli-failed" "exit failed" { };
}
