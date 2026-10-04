{ packages, url }:
let
  pkgs = import packages;
  upstream = import (packages + "/pkgs/lua-source.nix");
  fetchurl = src: pkgs.fetchurl (src // { inherit url; });
  liblua = import (packages + "/pkgs/liblua.nix") {
    inherit (pkgs) mkDerivation;
    inherit fetchurl upstream;
    config = /. + (packages + "/pkgs/lua-ape-config.h");
  };
in
import (packages + "/pkgs/lua.nix") {
  inherit (pkgs) mkDerivation;
  inherit fetchurl upstream liblua;
}
