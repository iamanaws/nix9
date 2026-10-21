let
  pkgs = import (
    builtins.fetchTarball {
      url = "https://example.org/packages.tar.gz";
      sha256 = "@sha256@";
    }
  );
in
pkgs.buildEnv {
  name = "updated-tools";
  paths = [ pkgs.sha1sum ];
}
