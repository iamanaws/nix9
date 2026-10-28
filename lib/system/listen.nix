{ configuration }:
(
  {
    enable ? false,
    tcp ? { },
  }:
  let
    error = message: throw "mkSystem: services.listen.${message}";
    ports = builtins.attrNames tcp;
    validPort = port: builtins.match "[1-9][0-9]{0,4}" port != null && builtins.fromJSON port <= 65535;
    validScript = script: builtins.isString script && builtins.match "[ \t\r\n]*" script == null;
  in
  if !builtins.isBool enable then
    error "enable must be a boolean"
  else if !builtins.isAttrs tcp then
    error "tcp must map numeric TCP ports to rc scripts"
  else if !builtins.all validPort ports then
    error "tcp ports must be canonical decimal numbers from 1 to 65535"
  else if !builtins.all (port: validScript tcp.${port}) ports then
    error "tcp scripts must be nonempty strings"
  else if !enable && tcp != { } then
    error "tcp requires services.listen.enable"
  else if !enable then
    null
  else
    tcp
)
  configuration
