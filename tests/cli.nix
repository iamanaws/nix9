let
  pkgs = import <nix9>;
in
pkgs.mkInstallation {
  name = "cli";
  machines.local = {
    ip = "10.0.2.90";
    configuration.services.ndb.dns.enable = false;
  };
}
