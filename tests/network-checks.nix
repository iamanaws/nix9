let
  fixtures = import ./networks.nix { };
  ndb = import ./ndb.nix;
  multinet = import ./ndb-multinet.nix { };
  ndbValid = [
    "initial"
    "changed"
    "perMachine"
    "composed"
    "missingRuntime"
  ];
  ndbRejected = builtins.mapAttrs (_: value: !(builtins.tryEval value.systems.cpu.drvPath).success) (
    builtins.removeAttrs multinet ndbValid
  );
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
assert builtins.isString ndb.minimal.drvPath;
assert builtins.isString ndb.included.drvPath;
assert builtins.all (value: value) (builtins.attrValues ndbRejected);
assert builtins.all (name: builtins.isString multinet.${name}.systems.cpu.drvPath) ndbValid;
assert multinet.initial.discovery.hosts.cpu.aliases == [ "compute" ];
assert multinet.initial.discovery.hosts.cpu.auth == null;
assert multinet.initial.discovery.networks.default.cpu == "cpu";
assert multinet.initial.discovery.networks.lab.auth == "auth-lab.example.test";
assert (builtins.head multinet.composed.discovery.records).sys == "module-record";
assert
  builtins.length multinet.composed.discovery.records
  == builtins.length multinet.initial.discovery.records + 1;
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
  ndbDefaults = [
    "minimal"
    "included"
  ];
  inherit ndbValid ndbRejected;
}
