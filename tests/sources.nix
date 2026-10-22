{ packages, url }:
let
  pkgs = import packages;
  upstream = import (packages + "/pkgs/lua/source.nix");
  fetchurl = src: pkgs.fetchurl (src // { inherit url; });
  liblua = import (packages + "/pkgs/liblua/default.nix") {
    inherit (pkgs) mkDerivation libap libbsd;
    inherit fetchurl upstream;
    config = /. + (packages + "/pkgs/lua/ape-config.h");
  };
in
import (packages + "/pkgs/lua/default.nix") {
  inherit (pkgs) mkDerivation;
  inherit fetchurl upstream liblua;
}
