{
  pkgs ? import <nix9>,
}:
let
  make =
    settings:
    pkgs.mkSystem {
      hostName = "store";
      machineId = "store";
      networking.enable = true;
      services.ndb = {
        enable = true;
        records = [
          {
            authdom = "nix9.shared";
            auth = "127.0.0.1";
          }
        ];
      };
      services.auth = {
        enable = true;
        keyDatabase = "/adm/shared.keys";
        requiredUsers = [
          "nixhost"
          "alice"
          "bob"
        ];
      };
      nix = settings;
    };
  settings = {
    daemon = {
      enable = true;
      keyFile = "/adm/nix-store.keys";
      keyPattern = "dom=nix9.shared user=nixhost";
    };
    settings.allowed-users = [
      "alice"
      "bob"
    ];
  };
  invalid =
    extra:
    pkgs.mkSystem {
      hostName = "store";
      nix = settings;
      imports = [ extra ];
    };
in
{
  initial = make settings;
  moved = make (
    pkgs.lib.recursiveUpdate settings {
      daemon.port = 17052;
      settings.allowed-users = [ "bob" ];
    }
  );
  disabled = make { };
  provisioned = make (pkgs.lib.recursiveUpdate settings { daemon.keyFile = null; });
  wildcard = make { daemon = settings.daemon; };
  empty = make (pkgs.lib.recursiveUpdate settings { settings.allowed-users = [ ]; });
  trusted = make (pkgs.lib.recursiveUpdate settings { settings.trusted-users = [ "builder" ]; });
  invalid = {
    anonymous = make (pkgs.lib.recursiveUpdate settings { settings.allowed-users = [ "none" ]; });
    group = make (pkgs.lib.recursiveUpdate settings { settings.allowed-users = [ "@wheel" ]; });
    trustedGroup = make (pkgs.lib.recursiveUpdate settings { settings.trusted-users = [ "@wheel" ]; });
    trustedAnonymous = make (
      pkgs.lib.recursiveUpdate settings { settings.trusted-users = [ "none" ]; }
    );
    trustedBadUser = make (
      pkgs.lib.recursiveUpdate settings { settings.trusted-users = [ "bad user" ]; }
    );
    badUser = make (pkgs.lib.recursiveUpdate settings { settings.allowed-users = [ "bad user" ]; });
    disabledTransport = make (pkgs.lib.recursiveUpdate settings { daemon.enable = false; });
    secretPattern = make (
      pkgs.lib.recursiveUpdate settings { daemon.keyPattern = "!password=secret"; }
    );
    storeKey = make (
      pkgs.lib.recursiveUpdate settings { daemon.keyFile = "/usr/local/nix/store/secret"; }
    );
    pathKey = make (pkgs.lib.recursiveUpdate settings { daemon.keyFile = ./store-service.nix; });
    traversal = make (pkgs.lib.recursiveUpdate settings { daemon.keyFile = "/adm/../secret"; });
    portRange = make (pkgs.lib.recursiveUpdate settings { daemon.port = 65536; });
    zeroPort = make (pkgs.lib.recursiveUpdate settings { daemon.port = 0; });
    cpuPort = make (pkgs.lib.recursiveUpdate settings { daemon.port = 17019; });
    negativeJobs = make { settings.max-jobs = -1; };
    multiline = make { settings.cores = "1\nallowed-users = *"; };
    comment = make { settings.builders = "cpu://build # ignored"; };
    invalidName = make { settings."include /tmp/policy" = ""; };
    manualConfig = invalid { files."nix.conf" = "allowed-users = *"; };
    removedJobs = make { maxJobs = 1; };
    scriptPort = invalid {
      services.listen = {
        enable = true;
        tcp."17051" = "echo conflict";
      };
    };
    exportPort = invalid {
      services.exports.data = {
        path = "/usr";
        port = 17051;
        allowedUsers = [ "alice" ];
      };
    };
    filesystemPort = invalid {
      services.cwfs = {
        enable = true;
        configDevice = "/adm/cwfs/config";
        port = 17051;
      };
    };
  };
}
