let
  pkgs = import <nix9>;
  system =
    logging:
    pkgs.mkSystem {
      hostName = "nix9-logs";
      inherit logging;
    };
  enabled = {
    enable = true;
    files = {
      nix9.mode = "0640";
      nix9-test.mode = "0600";
      nix9-new = { };
    };
  };
in
{
  one = system enabled;
  two = system (
    enabled
    // {
      files = {
        nix9.mode = "0600";
        nix9-test.mode = "0644";
        nix9-added = { };
      };
    }
  );
  disabled = system { };
  conflict = system {
    enable = true;
    files = {
      nix9-directory = { };
      nix9-should-not-exist = { };
    };
  };
  exclusive = system {
    enable = true;
    files.nix9-exclusive = { };
  };
  temporary = system {
    enable = true;
    files.nix9-temporary = { };
  };
  invalidEnable = system { enable = "yes"; };
  invalidFiles = system {
    enable = true;
    files = [ "nix9" ];
  };
  invalidName = system {
    enable = true;
    files."../escape" = { };
  };
  emptyName = system {
    enable = true;
    files."" = { };
  };
  optionName = system {
    enable = true;
    files."-x" = { };
  };
  invalidFile = system {
    enable = true;
    files.example = "0640";
  };
  invalidMode = system {
    enable = true;
    files.example.mode = "0999";
  };
  numericMode = system {
    enable = true;
    files.example.mode = 640;
  };
  readOnlyMode = system {
    enable = true;
    files.example.mode = "0444";
  };
  disabledFiles = system { files.example = { }; };
}
