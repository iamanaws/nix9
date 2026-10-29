let
  pkgs = import <nix9>;
  discovery = {
    enable = true;
    hosts = {
      fs1 = {
        ip = "10.0.2.2";
        dom = "fs1.nix9.test";
      };
      cpu1 = {
        ip = "10.0.2.200";
        dom = "cpu1.nix9.test";
        auth = "fs1";
        fs = "fs1";
      };
      terminal = {
        ip = "10.0.2.15";
        ether = "525400123456";
      };
    };
    networks.lab = {
      address = "10.0.2.0";
      prefixLength = 24;
      auth = "fs1";
      fs = "fs1";
      cpu = "cpu1";
      authdom = "nix9.test";
    };
  };
  system =
    name: ndb:
    pkgs.mkSystem {
      hostName = name;
      networking = {
        enable = true;
        # Keep DNS hint lookup independent of the host's upstream resolver.
        nameservers = [ "127.0.0.1" ];
      };
      services.ndb = ndb;
      files.version = name + "\n";
    };
in
{
  one = system "ndb-one" discovery;
  two = system "ndb-two" (discovery // { dns.enable = false; });
  disabled = system "ndb-disabled" { };
  invalidAddress = system "invalid" (discovery // { hosts.bad.ip = "300.1.1.1"; });
  duplicateAddress = system "invalid" (
    discovery
    // {
      hosts = {
        a.ip = "10.0.2.2";
        b.ip = "10.0.2.2";
      };
    }
  );
  missingHost = system "invalid" (
    discovery
    // {
      networks.lab = {
        address = "10.0.2.0";
        prefixLength = 24;
        fs = "missing";
      };
    }
  );
  invalidNetwork = system "invalid" (
    discovery
    // {
      networks.lab = {
        address = "10.0.2.1";
        prefixLength = 24;
      };
    }
  );
  invalidInclude = system "invalid" (discovery // { include = [ "/lib/ndb/local" ]; });
}
