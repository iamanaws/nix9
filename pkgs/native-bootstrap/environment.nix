let
  pkgs = import ./packages;
in
pkgs.buildEnv {
  name = "tools";
  paths = [
    pkgs.fortune
    pkgs.sha1sum
  ];
}
