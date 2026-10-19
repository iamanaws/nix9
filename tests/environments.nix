{ packages }:
let
  pkgs = import packages;
  command =
    name: executable: message:
    pkgs.mkDerivation {
      inherit name;
      src = builtins.toFile "command.c" ''
        #include <u.h>
        #include <libc.h>
        void main(void) { print("${message}\n"); exits(nil); }
      '';
      buildCommand = ''
        mkdir -p $out/bin
        6c -o command.6 $src
        6l -s -o $out/bin/${executable} command.6
      '';
    };
  first = command "choice-one" "nix9-choice" "one";
  second = command "choice-two" "nix9-choice" "two";
  oldOnly = command "old-command" "nix9-old-only" "old-only";
  newOnly = command "new-command" "nix9-new-only" "new-only";
  data = pkgs.mkDerivation {
    name = "environment-data";
    buildCommand = ''
      mkdir -p $out/share
      echo retained > $out/share/message
    '';
  };
in
{
  one = pkgs.buildEnv {
    name = "environment-one";
    paths = [
      first
      oldOnly
      data
    ];
  };
  two = pkgs.buildEnv {
    name = "environment-two";
    paths = [
      second
      newOnly
    ];
  };
  empty = pkgs.buildEnv {
    name = "environment-empty";
    paths = [ ];
  };
  duplicate = pkgs.buildEnv {
    name = "environment-duplicate";
    paths = [
      first
      first
    ];
  };
  collision = pkgs.buildEnv {
    name = "environment-collision";
    paths = [
      first
      second
    ];
  };
  tools = pkgs.buildEnv {
    name = "environment-tools";
    paths = [
      pkgs.lua
      pkgs.fortune
    ];
  };
}
