{ lib, pkgs, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.plumber = {
    enable = lib.mkEnableOption "plumber and its native rule file";
    rules = mkOption {
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
