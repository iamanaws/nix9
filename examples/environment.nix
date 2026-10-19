let
  pkgs = import /usr/local/pkg/native-packages;
in
pkgs.buildEnv {
  name = "tools";
  paths = [
    pkgs.lua
    pkgs.fortune
  ];
  files."/tmp/nix9.lua" = ''
    print("Hello from nix9")
  '';
}
