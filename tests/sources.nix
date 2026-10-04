{ packages, url }:
let
  pkgs = import packages;
  upstream = import (packages + "/pkgs/lua-source.nix");
in
import (packages + "/pkgs/lua.nix") {
  inherit (pkgs) mkDerivation fetchurl;
  upstream = upstream // {
    src = upstream.src // {
      inherit url;
    };
  };
  config = /. + (packages + "/pkgs/lua-ape-config.h");
}
