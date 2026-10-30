{ lib, ... }:
let
  inherit (import ./types.nix { inherit lib; }) runtimeFile;
in
{
  options.cwfs = {
    enable = lib.mkEnableOption "a separate cwfs64x data filesystem on a CPU server";
    configDevice = lib.mkOption {
      type = lib.types.nullOr runtimeFile;
      default = null;
      description = "Provisioned cwfs64x configuration device or file. Startup never initializes it.";
    };
    deviceMap = lib.mkOption {
      type = lib.types.attrsOf runtimeFile;
      default = { };
      description = "Map CWFS wren names, such as w0, to existing data devices or files.";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 564;
      description = "TCP port serving native authenticated 9P, including main and dump attaches.";
    };
    keyFile = lib.mkOption {
      type = lib.types.nullOr runtimeFile;
      default = null;
      description = "Owner-only runtime factotum key commands; null uses provisioned server keys.";
    };
    cachePercent = lib.mkOption {
      type = lib.types.ints.between 1 80;
      default = 10;
      description = "Percentage of available user memory used for CWFS buffers.";
    };
    autoDump = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Enable the native daily dump. Historical dumps remain on the archival device.";
    };
    dumpHour = lib.mkOption {
      type = lib.types.ints.between 0 23;
      default = 5;
      description = "Daily dump hour in the server's native timezone.";
    };
  };
}
