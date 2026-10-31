{
  lib,
  mkDerivation,
  configuration,
  packages,
}:
let
  inherit (configuration)
    enable
    font
    scroll
    windows
    acme
    plumbingRules
    ;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] (toString value) + "'";
  arguments = words: lib.concatMapStringsSep " " quote words;
  tools = mkDerivation {
    name = "nix9-session-tools";
    src = ./session-run.c;
    buildCommand = ''
      mkdir -p $out/bin
      6c -o session.6 $src
      6l -o $out/bin/nix9-session-run session.6
    '';
  };
  window =
    entry:
    "${packages.rio}/bin/window -m"
    + lib.optionalString (entry.directory != null) (" -cd " + quote entry.directory)
    + lib.optionalString (entry.rectangle != null) (" -r " + arguments entry.rectangle)
    + " "
    + arguments entry.command
    + "\n";
in
builtins.deepSeq configuration (
  if !enable then
    null
  else
    {
      packages = [
        packages.rio
        packages.plumber
        packages.rc
      ]
      ++ lib.optional acme.enable packages.acme;
      rules = plumbingRules + "\n";
      init = ''
        #!/bin/rc
        # Rio's startup command inherits the prepared session namespace.
        cd $home || exit 'cannot enter home directory'
        ${lib.optionalString acme.enable (window {
          directory = acme.directory;
          rectangle = acme.rectangle;
          command = [
            "${packages.acme}/bin/acme"
            "-c"
            (toString acme.columns)
            "-f"
            font
            "-F"
            acme.fixedFont
          ]
          ++ lib.optionals (acme.files != [ ]) ([ "--" ] ++ acme.files);
        })}
        ${lib.concatMapStrings window windows}
        status='''
      '';
      start = ''
        test -d /dev/draw && test -e /dev/mouse || {
          echo 'nix9-session: graphics and mouse devices are required' >[1=2]
          exit 'no display'
        }
        test -r ${quote font} ${lib.optionalString acme.enable ("&& test -r " + quote acme.fixedFont)} || {
          echo 'nix9-session: configured font is unavailable' >[1=2]
          exit 'font unavailable'
        }
        test -d $home || {
          echo 'nix9-session: home directory is unavailable' >[1=2]
          exit 'home unavailable'
        }
        ${lib.concatMapStrings
          (directory: ''
            test -d ${quote directory} || {
              echo 'nix9-session: working directory is unavailable:' ${quote directory} >[1=2]
              exit 'directory unavailable'
            }
          '')
          (
            lib.unique (
              builtins.filter (directory: directory != null) (
                map (entry: entry.directory) windows ++ lib.optional acme.enable acme.directory
              )
            )
          )
        }
        nix9GraphicalSession=$nix9System
        tabstop=${toString acme.tabStop}
        # Acme searches /bin directly, including when it runs shell commands.
        bind -b $nix9/bin /bin || exit 'cannot expose Nix commands'
        exec ${tools}/bin/nix9-session-run ${packages.plumber}/bin/plumber \
          $nix9System/session/plumbing ${packages.rio}/bin/rio \
          -f ${quote font} ${lib.optionalString scroll "-s"} -i $nix9System/session/init
      '';
    }
)
