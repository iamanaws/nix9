let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  imports = [
    (
      {
        lib,
        pkgs,
        config,
        ...
      }:
      {
        options.site.message = lib.mkOption { type = lib.types.str; };
        config = {
          hostName = lib.mkDefault "module-default";
          site.message = lib.mkDefault "default";
          packages = [ pkgs.fortune ];
          files.message = config.site.message + "\n";
        };
      }
    )
  ];
  hostName = "module-host";
  site.message = "imported and overridden";
  files.second = "merged\n";
  assertions = [
    {
      assertion = true;
      message = "valid configuration";
    }
  ];
}
