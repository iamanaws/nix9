{ configuration }:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
(
  {
    enable ? false,
    source ? "rtc",
    server ? null,
    port ? 123,
    rtcLocalTime ? false,
  }:
  let
    split = separator: value: builtins.filter builtins.isString (builtins.split separator value);
    validIP =
      ip:
      builtins.length (split "\\." ip) == 4
      && builtins.all (
        part: builtins.match "(0|[1-9][0-9]{0,2})" part != null && builtins.fromJSON part <= 255
      ) (split "\\." ip)
      && builtins.fromJSON (builtins.head (split "\\." ip)) > 0
      && builtins.fromJSON (builtins.head (split "\\." ip)) < 224;
    validServer =
      value:
      builtins.isString value
      && builtins.stringLength value <= 253
      && (
        if builtins.match "[0-9.]+" value != null then
          validIP value
        else
          builtins.all (
            label:
            builtins.stringLength label <= 63
            && builtins.match "[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?" label != null
          ) (split "\\." value)
      );
    error = message: throw "mkSystem: services.timesync.${message}";
    arguments =
      if source == "ntp" then
        "-n ${quote ("udp!" + server + "!" + toString port)}"
      else
        "-r${if rtcLocalTime then " -L" else ""}";
  in
  if !builtins.isBool enable then
    error "enable must be a boolean"
  else if
    !builtins.elem source [
      "rtc"
      "ntp"
    ]
  then
    error "source must be rtc or ntp"
  else if !builtins.isBool rtcLocalTime then
    error "rtcLocalTime must be a boolean"
  else if !builtins.isInt port || port < 1 || port > 65535 then
    error "port must be an integer from 1 to 65535"
  else if source == "ntp" && !validServer server then
    error "server must be a DNS hostname or unicast IPv4 address when source is ntp"
  else if source == "ntp" && rtcLocalTime then
    error "rtcLocalTime can only be used with the rtc source"
  else if source == "rtc" && server != null then
    error "server can only be used with the ntp source"
  else if source == "rtc" && port != 123 then
    error "port can only be changed with the ntp source"
  else if !enable then
    ""
  else
    ''
      # termrc starts aux/timesync after networking, with its native duplicate check.
      # Set this in the boot environment, never during session activation.
      TIMESYNCARGS=(${arguments})
    ''
)
  configuration
