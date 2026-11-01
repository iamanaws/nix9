{ lib, ... }:
let
  inherit (lib) mkOption types;
  address = types.addCheck types.str (
    value:
    let
      parts = lib.splitString "." value;
    in
    builtins.length parts == 4
    && builtins.all (
      part: builtins.match "(0|[1-9][0-9]{0,2})" part != null && builtins.fromJSON part <= 255
    ) parts
    && builtins.fromJSON (builtins.head parts) > 0
    && builtins.fromJSON (builtins.head parts) < 224
    && builtins.head parts != "127"
  );
in
{
  options.dhcpd = mkOption {
    default = { };
    description = "Native IPv4 DHCP serving from NDB.";
    type = types.submodule {
      options = {
        enable = lib.mkEnableOption "native IPv4 DHCP serving from NDB";
        pools = mkOption {
          default = [ ];
          description = "Dynamic address ranges, each given as a starting IPv4 address and a count. Empty serves only NDB reservations.";
          type = types.listOf (
            types.submodule {
              options = {
                start = mkOption {
                  type = address;
                  description = "First dynamic IPv4 address.";
                };
                count = mkOption {
                  type = types.ints.between 1 2147483647;
                  description = "Number of consecutive addresses, including start.";
                };
              };
            }
          );
        };
        minimumLease = mkOption {
          type = types.ints.between 1 2147483647;
          default = 900;
          description = "Native -M lease duration in seconds for dynamic clients that do not request one. Clients may request a different duration.";
        };
        staticLease = mkOption {
          type = types.ints.between 1 2147483647;
          default = 1800;
          description = "NDB reservation lease duration in seconds, at least minimumLease.";
        };
      };
    };
  };
}
