{
  pkgs ? import <nix9>,
}:
let
  make =
    session:
    pkgs.mkSystem {
      hostName = "graphical";
      inherit session;
    };
  initial = import <nix9/examples/workstation/configuration.nix>;
  controls = pkgs.mkDerivation {
    name = "graphical-test-controls";
    src = builtins.toFile "Graphctl" "#!/bin/rc\nrfork ne\nexec /amd64/bin/aux/listen1 -1 -t tcp!*!17023 /amd64/bin/rc -c 'prompt=(''acme% '' ''    ''); exec /amd64/bin/rc -i >[2=1]'\n";
    buildCommand = ''
      mkdir -p $out/bin
      cp $src $out/bin/Graphctl
      chmod 755 $out/bin/Graphctl
    '';
  };
  installation =
    extra:
    pkgs.mkInstallation {
      imports = [
        initial
        ({ lib, ... }: {
          machines.terminal.configuration.packages = [ controls ];
          machines.terminal.configuration.session.windows = lib.mkForce [
            {
              directory = "/n/projects/hello";
              rectangle = [
                8
                548
                1016
                760
              ];
              command = [
                "rc"
                "-c"
                (builtins.concatStringsSep "; " [
                  "echo $nix9GraphicalSession > /tmp/window-system"
                  "echo $tabstop > /tmp/window-tabs"
                  "pwd > /tmp/window-directory"
                  "nix9-session > /tmp/nested.log >[2=1]"
                  "echo $status > /tmp/nested.status"
                  "echo 'Edit hello.c in Acme, then run nix-build default.nix'"
                  "while(! test -e /tmp/build-now) sleep 0.1"
                  "nix-build default.nix --no-out-link > /tmp/graph-build.log >[2=1]"
                  "echo -n $status > /tmp/graph-build.status"
                  "cat /tmp/graph-build.log"
                  "exec rc -i"
                ])
              ];
            }
          ];
        })
        { machines.terminal.configuration = extra; }
      ];
    };
in
{
  inherit initial;
  first = installation { };
  second = installation (
    { lib, ... }: {
      session.acme.columns = 3;
      session.acme.tabStop = 8;
      session.acme.files = lib.mkForce [ "hello.c" ];
    }
  );
  disabled = installation { session.enable = pkgs.lib.mkForce false; };
  malformed = installation { session.plumbingRules = "not a plumbing rule\n"; };
  missingDirectory = installation {
    session.acme.directory = pkgs.lib.mkForce "/n/projects/missing";
  };
  missingFont = installation { session.font = "/usr/glenda/missing.font"; };
  invalid = {
    relativeFont = make { font = "font"; };
    traversalFont = make { font = "/lib/../other/font"; };
    multilineFont = make { font = "/lib/font\nother"; };
    emptyCommand = make { windows = [ { command = [ ]; } ]; };
    emptyProgram = make {
      windows = [
        {
          command = [
            ""
            "arg"
          ];
        }
      ];
    };
    multilineArgument = make {
      windows = [
        {
          command = [
            "rc"
            "bad\nargument"
          ];
        }
      ];
    };
    relativeDirectory = make { windows = [ { directory = "relative"; } ]; };
    rectangleSize = make {
      windows = [
        {
          rectangle = [
            1
            2
            3
          ];
        }
      ];
    };
    rectangleOrder = make {
      acme.rectangle = [
        100
        10
        20
        500
      ];
    };
    negativeRectangle = make {
      acme.rectangle = [
        (-1)
        0
        200
        200
      ];
    };
    zeroColumns = make { acme.columns = 0; };
    zeroTabs = make { acme.tabStop = 0; };
    unknownOption = make { restart = true; };
  };
}
