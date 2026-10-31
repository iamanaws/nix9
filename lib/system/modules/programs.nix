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
  options.programs.rio = {
    enable = lib.mkEnableOption "Rio and its native startup configuration";
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
  };
  options.programs.acme = {
    rectangle = mkOption {
      type = types.nullOr rectangle;
      default = null;
      description = "Editor window coordinates [ left top right bottom ]; null uses native placement.";
    };
    enable = mkOption {
      type = types.bool;
      default = false;
      description = "Install Acme and generate its native arguments.";
    };
    start = mkOption {
      type = types.bool;
      default = false;
      description = "Open the configured Acme window from Rio riostart.";
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
      default = config.programs.rio.font;
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
  config.assertions = [
    {
      assertion =
        !config.programs.acme.start || (config.programs.acme.enable && config.programs.rio.enable);
      message = "programs.acme.start requires programs.acme.enable and programs.rio.enable";
    }
  ];
}
