{
  lib,
  pkgs,
  config,
  ...
}:
let
  inherit (lib) mkOption types;
  word = types.addCheck types.str (value: builtins.match ".*[\r\n].*" value == null);
  absolute = types.addCheck word (
    value:
    lib.hasPrefix "/" value
    && (value == "/" || (!lib.hasSuffix "/" value && !lib.hasInfix "//" value))
    && builtins.all (part: part != "." && part != "..") (lib.splitString "/" value)
  );
  rectangle = types.addCheck (types.listOf types.ints.unsigned) (
    value:
    builtins.length value == 4
    && builtins.elemAt value 0 < builtins.elemAt value 2
    && builtins.elemAt value 1 < builtins.elemAt value 3
  );
in
{
  options.session = {
    enable = lib.mkEnableOption "a graphical user session started with nix9-session";
    font = mkOption {
      type = absolute;
      default = "${pkgs.fonts}/share/fonts/dejavu/dejavu.12.font";
      description = "Rio and default editor font, including any store dependency.";
    };
    scroll = mkOption {
      type = types.bool;
      default = true;
      description = "Scroll new Rio windows automatically.";
    };
    windows = mkOption {
      default = [ { } ];
      description = "Startup windows in declaration order.";
      type = types.listOf (
        types.submodule {
          options = {
            command = mkOption {
              type = types.addCheck (types.listOf word) (value: value != [ ] && builtins.head value != "");
              default = [
                "rc"
                "-i"
              ];
              description = "Program and arguments, passed without shell interpretation.";
            };
            directory = mkOption {
              type = types.nullOr absolute;
              default = null;
              description = "Working directory; null uses the user's home.";
            };
            rectangle = mkOption {
              type = types.nullOr rectangle;
              default = null;
              description = "Window coordinates [ left top right bottom ]; null uses native placement.";
            };
          };
        }
      );
    };
    acme = {
      rectangle = mkOption {
        type = types.nullOr rectangle;
        default = null;
        description = "Editor window coordinates [ left top right bottom ]; null uses native placement.";
      };
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Open an Acme window at session startup.";
      };
      columns = mkOption {
        type = types.ints.between 1 16;
        default = 2;
        description = "Initial number of Acme columns.";
      };
      tabStop = mkOption {
        type = types.ints.between 1 32;
        default = 4;
        description = "Tab width in characters in Rio and Acme.";
      };
      fixedFont = mkOption {
        type = absolute;
        default = config.session.font;
        description = "Acme's alternate font.";
      };
      directory = mkOption {
        type = types.nullOr absolute;
        default = null;
        description = "Editor working directory; null uses the user's home.";
      };
      files = mkOption {
        type = types.listOf word;
        default = [ ];
        description = "Files or directories to open, relative to the editor working directory.";
      };
    };
    plumbingRules = mkOption {
      type = types.lines;
      default = ''
        include ${pkgs.plumber}/share/plumb/fileaddr

        type is text
        data matches '([^:]+)('$addr')?'
        arg isfile $1
        data set $file
        attr add addr=$3
        plumb to edit

        type is text
        arg isdir $data
        data set $dir
        plumb to edit
      '';
      description = "Native plumbing rules. Defaults route existing files and directories to an open editor.";
    };
  };
}
