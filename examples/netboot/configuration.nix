{
  imports = [ ../netroot/configuration.nix ];
  machines = {
    auth.configuration.networking.interfaces.ether0 = {
      useDHCP = false;
      address = "10.0.2.100";
      prefixLength = 24;
    };
    files.configuration = {
      networking.interfaces.ether0 = {
        useDHCP = false;
        address = "10.0.2.101";
        prefixLength = 24;
      };
      services.dhcpd.enable = true;
      services.tftpd.enable = true;
    };
    build = {
      ether = "525400123462";
      boot.pxe = {
        provider = "files";
        settings.console = 0;
      };
    };
  };
}
