{ packages }:
let
  pkgs = import packages;
  data = pkgs.mkDerivation {
    name = "session-data";
    buildCommand = ''
      mkdir -p $out/share
      echo retained > $out/share/message
    '';
  };
in
{
  gc = pkgs.buildEnv {
    name = "gc-session";
    paths = [ pkgs.ramfs ];
    files."/tmp/nix9-gc.conf" = "${data}/share/message\n";
    namespace = "ramfs -m /mnt";
  };
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
