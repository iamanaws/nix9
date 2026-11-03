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
      services.nixStore = settings;
    };
  settings = {
    enable = true;
    allowedUsers = [
      "alice"
      "bob"
    ];
    keyFile = "/adm/nix-store.keys";
    keyPattern = "dom=nix9.shared user=nixhost";
  };
  invalid =
    extra:
    pkgs.mkSystem {
      hostName = "store";
      services.nixStore = settings;
      imports = [ extra ];
    };
in
{
  initial = make settings;
  moved = make (
    settings
    // {
      port = 17052;
      allowedUsers = [ "bob" ];
    }
  );
  disabled = make { };
  provisioned = make (settings // { keyFile = null; });
  invalid = {
    empty = make (settings // { allowedUsers = [ ]; });
    anonymous = make (settings // { allowedUsers = [ "none" ]; });
    wildcard = make (settings // { allowedUsers = [ "*" ]; });
    badUser = make (settings // { allowedUsers = [ "bad user" ]; });
    disabledPolicy = make (settings // { enable = false; });
    secretPattern = make (settings // { keyPattern = "!password=secret"; });
    storeKey = make (settings // { keyFile = "/usr/local/nix/store/secret"; });
    pathKey = make (settings // { keyFile = ./store-service.nix; });
    traversal = make (settings // { keyFile = "/adm/../secret"; });
    portRange = make (settings // { port = 65536; });
    zeroPort = make (settings // { port = 0; });
    cpuPort = make (settings // { port = 17019; });
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
