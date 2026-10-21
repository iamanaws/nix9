{ packages }:
let
  pkgs = import packages;
in
{
  configured = pkgs.buildEnv {
    name = "configured-session";
    paths = [ pkgs.ramfs ];
    files."/tmp/nix9-session.conf" = "session configuration\n";
    namespace = "ramfs -m /mnt";
  };
  failed = pkgs.buildEnv {
    name = "failed-session";
    paths = [ pkgs.ramfs ];
    namespace = ''
      ramfs -m /mnt
      exit setup-failed
    '';
  };
}
