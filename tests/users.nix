{
  pkgs ? import <nix9>,
}:
let
  users = {
    alice = {
      id = 1010;
      home = "/usr/alice";
    };
    bob = {
      id = 1011;
      home = "/usr/bob";
    };
    project = {
      id = 1012;
      leader = "alice";
      members = [
        "alice"
        "bob"
      ];
    };
  };
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        <nix9/examples/netroot/configuration.nix>
        extra
      ];
      inherit users;
      machines = {
        auth.configuration.services.auth.requiredUsers = [
          "alice"
          "bob"
          "files"
          "build"
          "glenda"
        ];
        files.configuration.services.cwfs.directories."/projects" = {
          owner = "alice";
          group = "project";
          mode = "0770";
        };
        build.configuration.services.cpu.allowedUsers = [
          "alice"
          "bob"
        ];
        auth.configuration.services.auth.speaksFor.build = [
          "alice"
          "bob"
        ];
      };
    };
  system =
    settings:
    pkgs.mkSystem {
      hostName = "files";
      services.cwfs = {
        enable = true;
        configDevice = "/adm/storage/config";
        inherit users;
      }
      // settings;
    };
in
{
  initial = make { };
  distributed = pkgs.mkInstallation { imports = [ <nix9/examples/users/configuration.nix> ]; };
  shared = system { };
  membership = system {
    users = users // {
      project = users.project // {
        members = [ "alice" ];
      };
    };
  };
  invalid = {
    duplicateId = system {
      users = users // {
        eve.id = 1010;
      };
    };
    badId = system { users.alice.id = 32768; };
    reservedName = system { users.none.id = 12; };
    badName = system { users."bad-name".id = 12; };
    duplicateMember = system {
      users.project = users.project // {
        members = [
          "alice"
          "alice"
        ];
      };
    };
    protectedDirectory = system {
      directories."/adm/users" = {
        owner = "alice";
        group = "alice";
      };
    };
    unspecifiedOwner = system { directories."/projects" = { }; };
    disabledSettings = system { enable = false; };
    disabledAuth = pkgs.mkSystem {
      hostName = "auth";
      services.auth.requiredUsers = [ "alice" ];
    };
    inventoryOverride =
      (make (
        { lib, ... }: { machines.files.configuration.services.cwfs.users.alice.id = lib.mkForce 1234; }
      )).build;
  };
}
