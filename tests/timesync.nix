let
  pkgs = import <nix9>;
  fixture = import ./timesync-server.nix;
  system =
    timesync:
    pkgs.mkSystem {
      hostName = "nix9-clock";
      networking.enable = true;
      services.timesync = timesync;
    };
  rtc = {
    enable = true;
    source = "rtc";
  };
  ntp = {
    enable = true;
    source = "ntp";
    server = "10.0.2.2";
    port = fixture.port;
  };
in
{
  inherit (fixture) port;
  utc = system rtc;
  local = system (rtc // { rtcLocalTime = true; });
  ntp = system ntp;
  disabled = system { };
  invalidEnable = system { enable = "yes"; };
  invalidSource = system (rtc // { source = "file"; });
  invalidSourceType = system (rtc // { source = 1; });
  invalidLocalTime = system (rtc // { rtcLocalTime = "yes"; });
  missingServer = system (builtins.removeAttrs ntp [ "server" ]);
  invalidServerType = system (ntp // { server = [ "10.0.2.2" ]; });
  invalidServer = system (ntp // { server = "time.example.org\nreboot"; });
  invalidIP = system (ntp // { server = "10.0.2.256"; });
  ambiguousIP = system (ntp // { server = "010.0.2.2"; });
  multicastIP = system (ntp // { server = "224.0.0.1"; });
  unspecifiedIP = system (ntp // { server = "0.0.0.0"; });
  invalidHostname = system (ntp // { server = "time..example.org"; });
  serverOption = system (ntp // { server = "-D"; });
  serverPort = system (ntp // { server = "10.0.2.2!123"; });
  invalidPort = system (ntp // { port = 0; });
  invalidHighPort = system (ntp // { port = 65536; });
  invalidPortType = system (ntp // { port = "123"; });
  ntpLocalTime = system (ntp // { rtcLocalTime = true; });
  rtcServer = system (rtc // { server = "time.example.org"; });
  rtcPort = system (rtc // { port = 124; });
}
