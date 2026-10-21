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
  multiple =
    mk "cli-multiple"
      ''
        /bin/echo $out > /tmp/nix9-cli-multiple-out
        /bin/echo output > $out
        /bin/echo headers > $dev
      ''
      {
        outputs = [
          "out"
          "dev"
        ];
      };
  checked =
    mk "cli-checked"
      ''
        /bin/echo ran >> /tmp/nix9-check-count
        /bin/echo $out > $out
        /bin/cat /tmp/nix9-check-message >> $out
        if(/bin/test -e /tmp/nix9-check-fail) {
          /bin/echo check-builder-failed
          exit failed
        }
        if(! /bin/test -e /tmp/nix9-check-missing) {
          /bin/echo $out > $dev
          /bin/echo $dev >> $dev
          /bin/echo $devPlaceholder >> $dev
        }
        /bin/test -e $out
      ''
      {
        outputs = [
          "out"
          "dev"
        ];
        devPlaceholder = builtins.placeholder "dev";
      };
  failed = mk "cli-failed" "exit failed" { };
}
