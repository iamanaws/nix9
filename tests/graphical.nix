{
  pkgs ? import <nix9>,
}:
let
  make =
    session:
    pkgs.mkSystem {
      hostName = "graphical";
      programs.rio = builtins.removeAttrs session [ "acme" ];
      programs.acme = session.acme or { };
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
          machines.terminal.configuration.programs.rio.windows = lib.mkForce [
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
                  "echo $nix9System > /tmp/window-system"
                  "echo $tabstop > /tmp/window-tabs"
                  "pwd > /tmp/window-directory"
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
      programs.acme.columns = 3;
      programs.acme.tabStop = 8;
      programs.acme.files = lib.mkForce [ "hello.c" ];
    }
  );
  disabled = installation {
    programs.rio.enable = pkgs.lib.mkForce false;
    programs.acme.enable = pkgs.lib.mkForce false;
    programs.acme.start = pkgs.lib.mkForce false;
    services.plumber.enable = pkgs.lib.mkForce false;
  };
  malformed = installation { services.plumber.rules = "not a plumbing rule\n"; };
  missingDirectory = installation {
    programs.acme.directory = pkgs.lib.mkForce "/n/projects/missing";
  };
  missingFont = installation { programs.rio.font = "/usr/glenda/missing.font"; };
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
