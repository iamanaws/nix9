{ lib, ... }:
let
  inherit (lib) mkOption types;
  text = types.str;
  scalar = types.either text types.int;
  recordLine = types.attrsOf (types.either scalar (types.listOf scalar));
  nullable =
    description:
    mkOption {
      type = types.nullOr text;
      default = null;
      inherit description;
    };
  strings =
    description:
    mkOption {
      type = types.listOf text;
      default = [ ];
      inherit description;
    };
  defaults = {
    auth = nullable "Native authentication server name or address.";
    fs = nullable "Native file server name or address.";
    cpu = nullable "Native CPU server name or address.";
    authdom = nullable "Authentication domain.";
    ipgw = nullable "IPv4 gateway.";
    dns = strings "IPv4 DNS server addresses.";
    dnsdomain = strings "DNS search domains, in order.";
    ntp = strings "NTP server names or addresses.";
    bootf = nullable "Native boot file path supplied by BOOTP/DHCP.";
    tftp = nullable "TFTP server name or address.";
  };
in
{
  options = {
    enable = lib.mkEnableOption "the native network database and cs/DNS tools";
    hosts = mkOption {
      default = { };
      description = "Host records keyed by their canonical sys name.";
      type = types.attrsOf (
        types.submodule {
          options = defaults // {
            ip = mkOption {
              type = text;
              description = "Primary IPv4 address.";
            };
            aliases = strings "Additional sys names for this host.";
            dom = nullable "Fully qualified DNS name.";
            ether = nullable "Ethernet address associated with the primary IP.";
            extraAddresses = mkOption {
              default = [ ];
              description = "Additional IPv4 addresses, each on its own NDB line.";
              type = types.listOf (
                types.submodule {
                  options = {
                    ip = mkOption {
                      type = text;
                      description = "IPv4 address.";
                    };
                    ether = nullable "Ethernet address associated with this IP.";
                    ipgw = nullable "Gateway associated with this IP.";
                  };
                }
              );
            };
          };
        }
      );
    };
    networks = mkOption {
      default = { };
      description = "Native ipnet records; more specific subnets override parent defaults.";
      type = types.attrsOf (
        types.submodule {
          options = defaults // {
            address = mkOption {
              type = text;
              description = "Aligned IPv4 network address.";
            };
            prefixLength = mkOption {
              type = types.ints.between 0 32;
              description = "IPv4 prefix length.";
            };
          };
        }
      );
    };
    records = mkOption {
      type = types.listOf (types.either recordLine (types.listOf recordLine));
      default = [ ];
      description = "NDB records after hosts and networks. An attribute set is one record; a list of attribute sets is one record with several lines. List values repeat an attribute; empty strings represent flags.";
    };
    extraConfig = mkOption {
      type = types.lines;
      default = "";
      description = "Raw NDB text after generated records.";
    };
    include = mkOption {
      type = types.listOf text;
      default = [
        "/lib/ndb/common"
        "/cfg/nix9/ndb-original"
      ];
      description = "Files searched after generated records, in order. Paths under /cfg/nix9/files refer to this generation's files.";
    };
    dns = mkOption {
      default = { };
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Start native DNS at boot.";
          };
          resolver = mkOption {
            type = types.bool;
            default = true;
            description = "Use native DNS resolver mode.";
          };
          listenAddresses = strings "IPv4 addresses to serve over UDP/TCP port 53, or [ \"*\" ] for all local addresses. Empty keeps DNS local to /net/dns.";
          recursion = mkOption {
            type = types.enum [
              "none"
              "local"
              "all"
            ];
            default = "local";
            description = "Answer recursive network queries from no clients, directly connected networks, or all clients. Local /net/dns queries are unaffected.";
          };
        };
      };
      description = "Native DNS startup settings.";
    };
  };
}
