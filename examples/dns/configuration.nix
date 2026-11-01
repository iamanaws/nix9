{ ... }:
{
  name = "site-dns";
  ndb = {
    hosts = {
      dns = {
        dom = "ns.lab.example.test";
      };
      terminal.dom = "terminal.lab.example.test";
      build = {
        ip = "172.23.0.30";
        dom = "build.lab.example.test";
      };
    };
    records = [
      [
        {
          dom = "lab.example.test";
          soa = "";
          ns = "ns.lab.example.test";
        }
        {
          mx = "mail1.lab.example.test";
          pref = 10;
        }
        {
          mx = "mail2.lab.example.test";
          pref = 20;
        }
      ]
      {
        dom = "0.23.172.in-addr.arpa";
        soa = "";
        ns = "ns.lab.example.test";
      }
      {
        dom = "v6.lab.example.test";
        ip = "2001:db8::30";
      }
      {
        dom = "www.lab.example.test";
        cname = "build.lab.example.test";
      }
      {
        dom = "mail1.lab.example.test";
        ip = "172.23.0.40";
      }
      {
        dom = "mail2.lab.example.test";
        ip = "172.23.0.41";
      }
    ];
  };
  machines = {
    dns = {
      ip = "172.23.0.10";
      configuration = {
        networking = {
          enable = true;
          primaryInterface = "ether1";
          interfaces = {
            ether0 = { };
            ether1 = {
              useDHCP = false;
              address = "172.23.0.10";
              prefixLength = 24;
            };
          };
        };
        services.ndb.dns = {
          listenAddresses = [ "172.23.0.10" ];
          recursion = "none";
          resolver = false;
        };
      };
    };
    terminal = {
      ip = "172.23.0.20";
      configuration.networking = {
        enable = true;
        interfaces.ether0 = {
          useDHCP = false;
          address = "172.23.0.20";
          prefixLength = 24;
        };
        nameservers = [ "172.23.0.10" ];
      };
    };
  };
}
