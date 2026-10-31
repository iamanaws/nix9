{
  lib,
  manifest,
  configs,
}:
let
  lines = items: lib.concatStringsSep "\n" items + "\n";
  availability = required: if required then "required" else "optional";
in
{
  header = lines (
    [ "Installation ${manifest.name}" ]
    ++ lib.mapAttrsToList (name: value: "  ${name}: ${value}") (
      lib.filterAttrs (_: value: value != null) manifest.defaults
    )
  );
  machines = lib.mapAttrs (
    name: machine:
    lines (
      [
        ""
        name
        "  identity: ${machine.machineId}"
        "  NDB: sys=${machine.hostName} ip=${machine.ip}"
      ]
      ++ lib.optional (machine.endpoints.auth != null) "  auth: ${machine.endpoints.auth}"
      ++ lib.optional (machine.endpoints.cpu != null) "  CPU: ${machine.endpoints.cpu}"
      ++ lib.optional (
        machine.endpoints.cwfs != null
      ) "  CWFS: ${machine.endpoints.cwfs.address}, attaches main and dump"
      ++ lib.mapAttrsToList (
        export: settings:
        "  export ${export}: ${configs.${name}.services.exports.${export}.path} at ${settings.address}, "
        + (if settings.readOnly then "read-only" else "writable")
      ) machine.endpoints.exports
      ++ lib.mapAttrsToList (port: address: "  TCP ${port}: ${address}") machine.endpoints.tcp
      ++ lib.mapAttrsToList (
        mount: settings:
        "  mount ${mount}: "
        + (
          if settings ? provider then
            "${settings.provider} "
            + (if settings ? fileSystem then "attach ${settings.fileSystem}" else "export ${settings.export}")
          else
            settings.address + lib.optionalString (settings.attach != "") " attach ${settings.attach}"
        )
        + " at ${settings.mountPoint}, ${settings.transport}, ${availability settings.required}"
      ) machine.mounts
      ++ map (
        binding:
        "  bind: ${binding.source} at ${binding.target}, ${binding.mode}"
        + lib.optionalString binding.create ", create"
        + ", ${availability binding.required}"
      ) configs.${name}.namespace.binds
      ++ lib.mapAttrsToList (builder: settings: "  builder ${builder}: ${settings.host}") machine.builders
      ++ lib.optionals (machine.boot != null) [
        "  boot: ${machine.boot.provider} attach main, root ${machine.boot.root}"
        "  state: ${machine.boot.stateDirectory}"
      ]
      ++ lib.mapAttrsToList (
        job: settings: "  job ${job}: ${settings.schedule} as ${settings.user} on ${settings.target}"
      ) (lib.filterAttrs (_: settings: settings.scheduler == name) manifest.jobs)
      ++ [
        (
          "  deployment: "
          + (if machine.deployment.remote then "CPU at ${machine.deployment.host}" else "local")
        )
      ]
    )
  ) manifest.machines;
}
