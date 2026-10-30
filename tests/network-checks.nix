let
  fixtures = import ./networks.nix { };
  positive = [
    "dhcp"
    "dns"
    "static"
    "dual"
    "dualDHCP"
    "secondPrimary"
    "merged"
  ];
  rejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.drvPath).success) (
    builtins.removeAttrs fixtures positive
  );
  lab = import <nix9/examples/network-server> { };
  scenario = import ./network-server.nix { };
in
assert builtins.all (name: builtins.isString fixtures.${name}.drvPath) positive;
assert builtins.all (value: value) (builtins.attrValues rejected);
assert builtins.all (name: builtins.isString lab.systems.${name}.drvPath) [
  "auth"
  "labnet"
  "cpu"
  "terminal"
];
assert builtins.isString lab.systems.device.drvPath;
assert lab.manifest.machines.labnet.endpoints.exports.lab.readOnly == false;
assert lab.manifest.machines.cpu.mounts.lab.provider == "labnet";
assert builtins.all (name: builtins.isString scenario.${name}.drvPath) [
  "auth"
  "labnet"
  "cpu"
  "terminal"
  "moved"
  "device"
  "disabled"
];
{
  status = "passed";
  inherit positive rejected;
}
