{ lib }:
let
  inherit (lib) mkOption types;
  inherit (import ./types.nix { inherit lib; }) userName publicKeyPattern;
  number = value: builtins.fromJSON value;
  field =
    low: high: value:
    value == "*"
    || builtins.all (
      part:
      let
        range = lib.splitString "-" part;
        valid = builtins.all (n: builtins.match "(0|[1-9][0-9]?)" n != null) range;
        values = map number range;
      in
      valid
      && builtins.length range <= 2
      && builtins.all (n: n >= low && n <= high) values
      && (builtins.length values == 1 || builtins.head values <= lib.last values)
    ) (lib.splitString "," value);
  schedule = types.addCheck types.str (
    value:
    let
      fields = lib.splitString " " value;
    in
    builtins.length fields == 5
    && builtins.all (x: x) (
      lib.imap0 (
        i: v: field (builtins.elemAt [ 0 0 1 1 0 ] i) (builtins.elemAt [ 59 23 31 12 6 ] i) v
      ) fields
    )
  );
in
{
  inherit schedule;
  options = {
    schedule = mkOption {
      type = schedule;
      description = "Native cron fields: minute hour day month weekday. Supports *, numbers, ranges and lists.";
    };
    user = mkOption {
      type = userName;
      description = "Native account used on the scheduler and target.";
    };
    command = mkOption {
      type = types.lines;
      description = "rc commands to execute on the target.";
    };
    packages = mkOption {
      type = types.listOf types.package;
      default = [ ];
      description = "Packages available to the command and retained while it runs.";
    };
    keyPattern = mkOption {
      type = publicKeyPattern;
      default = "";
      description = "Public factotum attributes for remote CPU authentication.";
    };
    timeout = mkOption {
      type = types.ints.between 1 300;
      default = 10;
      description = "Seconds allowed to establish a remote CPU session.";
    };
  };
}
