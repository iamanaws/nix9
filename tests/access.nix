{
  pkgs ? import <nix9>,
}:
let
  system =
    services:
    pkgs.mkSystem {
      hostName = "access-test";
      inherit services;
    };
  cpu = {
    enable = true;
    allowedUsers = [ "glenda" ];
  };
in
{
  invalidEnable = system { cpu.enable = "yes"; };
  emptyUsers = system { cpu.enable = true; };
  invalidUser = system {
    cpu = cpu // {
      allowedUsers = [ "*" ];
    };
  };
  relativeKey = system {
    cpu = cpu // {
      keyFile = "keys";
    };
  };
  storedKey = system {
    cpu = cpu // {
      keyFile = "${pkgs.rcpu}/keys";
    };
  };
  literalKey = system {
    cpu = cpu // {
      keyFile = ./rcpu.nix;
    };
  };
  secretPattern = system {
    cpu = cpu // {
      keyPattern = "!password=example";
    };
  };
  disabledCPU = system { cpu.allowedUsers = [ "glenda" ]; };
  cpuPort = system {
    inherit cpu;
    listen = {
      enable = true;
      tcp."17019" = "echo conflict";
    };
  };
  authPort = system {
    auth.enable = true;
    listen = {
      enable = true;
      tcp."567" = "echo conflict";
    };
  };
  storedDatabase = system {
    auth = {
      enable = true;
      keyDatabase = "/usr/local/nix/store/keys";
    };
  };
  invalidSpeaker = system {
    auth = {
      enable = true;
      speaksFor."*" = [ "glenda" ];
    };
  };
  invalidDelegate = system {
    auth = {
      enable = true;
      speaksFor.cpu1 = [ "*" ];
    };
  };
  disabledAuth = system { auth.speaksFor.cpu1 = [ "glenda" ]; };
}
