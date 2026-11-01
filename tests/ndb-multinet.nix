{
  pkgs ? import <nix9>,
}:
let
  make =
    extra:
    pkgs.mkInstallation {
      imports = [
        (<nix9> + "/examples/discovery/configuration.nix")
        ({ lib, ... }: {
          ndb = {
            include = lib.mkAfter [
              "/cfg/nix9/files/site.ndb"
              "/cfg/nix9/files/fallback.ndb"
            ];
            extraConfig = ''
              sys=raw-record ip=192.0.2.201
            '';
            records = [
              {
                sys = "record-values";
                description = "build cache #1";
                tag = [
                  "first"
                  "second"
                ];
                restricted = "";
              }
            ];
          };
          machines = lib.genAttrs [ "cpu" "terminal" ] (_: {
            configuration.files = {
              "site.ndb" = ''
                sys=build-cache ip=192.0.2.80
                sys=ordered ip=192.0.2.81
              '';
              "fallback.ndb" = ''
                sys=ordered ip=192.0.2.82
              '';
            };
          });
        })
        extra
      ];
    };
in
{
  initial = make { };
  changed = make (
    { lib, ... }: {
      machines.cpu.configuration.files."site.ndb" = lib.mkForce ''
        sys=build-cache ip=192.0.2.90
        sys=ordered ip=192.0.2.91
      '';
    }
  );
  perMachine = make (
    { lib, ... }: {
      machines.terminal.configuration.services.ndb.hosts.cpu.dom = lib.mkForce "cpu.local.test";
    }
  );
  composed = make {
    ndb = { lib, pkgs, ... }: {
      records = lib.mkBefore [
        {
          sys = "module-record";
          ip = "192.0.2.200";
          tool = "${pkgs.ndb}";
        }
      ];
    };
  };
  missingFile = make (
    { lib, ... }: {
      ndb.include = lib.mkForce [ "/cfg/nix9/files/missing.ndb" ];
    }
  );
  missingRuntime = make (
    { lib, ... }: {
      ndb.include = lib.mkForce [ "/tmp/missing-site.ndb" ];
    }
  );
  duplicateAlias = make { ndb.hosts.terminal.aliases = [ "compute" ]; };
  duplicateExtraAddress = make { ndb.hosts.terminal.extraAddresses = [ { ip = "172.23.0.10"; } ]; };
  invalidGateway = make { ndb.networks.lab.ipgw = "999.1.1.1"; };
  overriddenAddress = make (
    { lib, ... }: {
      ndb.hosts.cpu.ip = lib.mkForce "192.0.2.100";
    }
  );
  removedHost = make (
    { lib, ... }: {
      ndb.hosts = lib.mkForce { };
    }
  );
  unknownSetting = make { ndb.hosts.cpu.unrecognised = "bad"; };
  emptyRecord = make { ndb.records = [ { } ]; };
  emptyRecordLines = make { ndb.records = [ [ ] ]; };
  emptyRecordValues = make { ndb.records = [ { sys = [ ]; } ]; };
  invalidRecordName = make { ndb.records = [ { "sys=bad" = "injected"; } ]; };
  longRecordName = make { ndb.records = [ { abcdefghijklmnopqrstuvwxyzabcdef = "truncated"; } ]; };
  invalidRecordValue = make { ndb.records = [ { sys = "bad\nrecord"; } ]; };
  invalidRecordQuote = make { ndb.records = [ { sys = "bad\"record"; } ]; };
  invalidRecordType = make { ndb.records = [ { port = true; } ]; };
}
