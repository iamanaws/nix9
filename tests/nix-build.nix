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
  dependency = mk "repair-dependency" "/bin/echo dependency > $out" { };
in
{
  inherit dependency;
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
  repair =
    mk "cli-repair"
      ''
        /bin/echo ran >> /tmp/nix9-repair-count
        if(! /bin/test -e /tmp/nix9-repair-missing) {
          /bin/mkdir $out
          /bin/echo original > $out/message
          /bin/echo $out > $out/self
          /bin/echo $input > $out/dependency
          if(/bin/test -e /tmp/nix9-repair-cycle) /bin/echo $dev >> $out/dependency
        }
        /bin/echo headers > $dev
        if(/bin/test -e /tmp/nix9-repair-change) /bin/echo changed > $dev
        if(/bin/test -e /tmp/nix9-repair-cycle) /bin/echo $out > $dev
        if(/bin/test -e /tmp/nix9-repair-fail) {
          /bin/echo repair-builder-failed
          exit failed
        }
        if(/bin/test -e /tmp/nix9-repair-cancel) {
          /bin/echo $pid > /tmp/nix9-repair-pid
          @{/bin/rc -c '/bin/echo $pid > /tmp/nix9-repair-child; exec /bin/sleep 30'}
        }
        /bin/echo finished
      ''
      {
        outputs = [
          "out"
          "dev"
        ];
        input = dependency;
      };
  fixedRepair =
    mk "fixed-repair"
      ''
        /bin/echo fixed > $out
        if(/bin/test -e /tmp/nix9-fixed-wrong) /bin/echo wrong > $out
        /bin/echo finished
      ''
      {
        outputHashMode = "flat";
        outputHashAlgo = "sha256";
        outputHash = builtins.hashString "sha256" "fixed\n";
      };
  failed = mk "cli-failed" "exit failed" { };
}
