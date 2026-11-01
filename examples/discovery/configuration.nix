{ ... }:
{
  name = "discovery";
  defaults.cpu = "cpu";
  ndb = {
    hosts = {
      cpu = {
        aliases = [ "compute" ];
        dom = "cpu.example.test";
        ether = "525400123456";
        ipgw = "10.0.2.2";
        extraAddresses = [
          {
            ip = "172.23.0.10";
            ether = "525400123457";
            ipgw = "172.23.0.1";
          }
        ];
      };
      terminal.fs = "files-workstation.example.test";
      lab-probe.ip = "172.23.0.30";
      site-probe.ip = "172.24.0.30";
    };
    networks = {
      default = {
        auth = "auth-site.example.test";
        fs = "files-site.example.test";
        authdom = "site.example.test";
      };
      site = {
        address = "172.16.0.0";
        prefixLength = 12;
        ntp = [ "time.example.test" ];
      };
      lab = {
        address = "172.23.0.0";
        prefixLength = 24;
        auth = "auth-lab.example.test";
        fs = "files-lab.example.test";
        authdom = "lab.example.test";
        dnsdomain = [
          "lab.example.test"
          "example.test"
        ];
      };
    };
    records = [
      {
        authdom = "partner.example.test";
        auth = "192.0.2.12";
      }
      {
        tcp = "artifacts";
        port = 17050;
      }
      [
        {
          dom = "example.test";
          soa = "";
        }
        { ns = "ns.example.test"; }
        {
          mx = "mail1.example.test";
          pref = 10;
        }
        {
          mx = "mail2.example.test";
          pref = 20;
        }
      ]
      {
        dom = "ns.example.test";
        ip = "127.0.0.1";
      }
      {
        sys = "ipv6-example";
        ip = "2001:db8::10";
      }
    ];
  };
  machines = {
    cpu = {
      ip = "10.0.2.15";
      configuration = {
        networking = {
          enable = true;
          interfaces = {
            ether0 = { };
            ether1 = {
              useDHCP = false;
              address = "172.23.0.10";
              prefixLength = 24;
            };
          };
        };
        services.cpu = {
          enable = true;
          allowedUsers = [ "glenda" ];
        };
      };
    };
    terminal = {
      ip = "172.23.0.20";
      configuration = {
        networking = {
          enable = true;
          interfaces.ether0 = {
            useDHCP = false;
            address = "172.23.0.20";
            prefixLength = 24;
          };
        };
      };
    };
  };
}
