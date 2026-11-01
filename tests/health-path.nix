let
  pkgs = import <nix9>;
in
pkgs.mkSystem {
  hostName = "health-path";
  namespace.mounts.work = {
    address = "tcp!files!564";
    transport = "tcp";
    attach = "main";
    keyPattern = "dom=nix9.storage";
  };
  namespace.binds = [
    {
      source = "/n/work/missing-workspace";
      target = "/tmp/health-path";
    }
  ];
}
