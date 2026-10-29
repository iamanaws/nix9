{
  lib,
  packages,
  mkDerivation,
  buildEnv,
}:
configuration:
let
  inventory =
    (lib.evalModules {
      class = "nix9-installation";
      specialArgs.pkgs = packages;
      modules = [
        ./options.nix
        configuration
      ];
    }).config;
  inherit (inventory)
    name
    defaults
    machines
    jobs
    ;
  makeJob = import ../system/job.nix { inherit mkDerivation buildEnv; };
  tasks = lib.mapAttrs (name: job: makeJob (job // { inherit name; })) jobs;
  scheduledJobs =
    machine:
    lib.mapAttrs (
      _: job:
      (builtins.removeAttrs job [ "scheduler" ])
      // {
        target = if job.target == machine then null else machines.${job.target}.hostName;
      }
    ) (lib.filterAttrs (_: job: job.scheduler == machine) jobs);
  targetJobs = machine: lib.filterAttrs (_: job: job.target == machine) jobs;
  names = builtins.attrNames machines;
  error = message: throw "mkInstallation: ${message}";
  unique = items: builtins.length items == builtins.length (lib.unique items);
  label =
    value:
    builtins.stringLength value <= 63 && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" value != null;
  providers = builtins.filter (kind: defaults.${kind} != null) [
    "auth"
    "fs"
    "cpu"
  ];
  providerNames = map (kind: defaults.${kind}) providers;
  discoveryDefaults =
    builtins.listToAttrs (
      map (kind: lib.nameValuePair kind machines.${defaults.${kind}}.hostName) providers
    )
    // lib.optionalAttrs (defaults.authdom != null) { inherit (defaults) authdom; };
  discovery = {
    enable = true;
    hosts = lib.mapAttrs' (
      _: machine: lib.nameValuePair machine.hostName ({ inherit (machine) ip; } // discoveryDefaults)
    ) machines;
  };
  ndb = import ../system/ndb.nix {
    configuration = discovery;
    package = packages.ndb;
  };
  mountConfigurations = lib.mapAttrs (
    _: machine:
    lib.mapAttrs (_: mount: {
      inherit (mount)
        mountPoint
        keyPattern
        required
        timeout
        ;
      address = endpoint mount.provider configs.${mount.provider}.services.exports.${mount.export}.port;
    }) machine.mounts
  ) machines;
  configs = lib.mapAttrs (
    machineName: machine:
    (import ../system/eval.nix
      {
        inherit lib;
        pkgs = packages;
      }
      {
        imports = [ machine.configuration ];
        inherit (machine) hostName machineId;
        services.ndb = discovery;
        namespace.mounts = mountConfigurations.${machineName};
        services.cron = lib.mkIf (scheduledJobs machineName != { }) {
          enable = true;
          jobs = scheduledJobs machineName;
        };
        packages = lib.mapAttrsToList (name: _: tasks.${name}) (targetJobs machineName);
        directories = lib.mkMerge (
          lib.mapAttrsToList (_: job: {
            "/sys/log/nix9-jobs/${job.user}" = {
              mode = lib.mkDefault "0700";
              owner = lib.mkDefault job.user;
            };
          }) (targetJobs machineName)
        );
        assertions = [
          {
            assertion = builtins.all (
              name: configs.${machineName}.services.cron.jobs.${name} == (scheduledJobs machineName).${name}
            ) (builtins.attrNames (scheduledJobs machineName));
            message = "installation inventory owns scheduled jobs for ${machineName}";
          }
          {
            assertion =
              configs.${machineName}.machineId == machine.machineId
              && configs.${machineName}.hostName == machine.hostName;
            message = "installation inventory owns machineId and hostName for ${machineName}";
          }
          {
            assertion =
              configs.${machineName}.services.ndb.enable
              && configs.${machineName}.services.ndb.hosts == discovery.hosts;
            message = "installation inventory owns NDB hosts for ${machineName}";
          }
          {
            assertion = builtins.all (
              mountName:
              configs.${machineName}.namespace.mounts.${mountName}
              == mountConfigurations.${machineName}.${mountName}
            ) (builtins.attrNames machine.mounts);
            message = "installation inventory owns named mounts for ${machineName}";
          }
        ];
      }
    ).config
  ) machines;
  endpoint = provider: port: "tcp!${machines.${provider}.hostName}!${toString port}";
  serves =
    provider: kind:
    if kind == "fs" then
      configs.${provider}.services.exports != { }
    else
      configs.${provider}.services.${kind}.enable;
  mounts = lib.concatMap (
    consumer:
    lib.mapAttrsToList (mountName: mount: {
      inherit consumer mountName mount;
    }) machines.${consumer}.mounts
  ) names;
  buildSystem = import ../system/from-config.nix {
    inherit
      lib
      packages
      mkDerivation
      buildEnv
      ;
  };
  systems = builtins.mapAttrs (_: buildSystem) configs;
  dependencies =
    (lib.concatMap (
      consumer:
      let
        clientMounts = builtins.attrValues configs.${consumer}.namespace.mounts;
        servesUsers = serves consumer "cpu" || serves consumer "fs";
      in
      lib.optional
        (defaults.auth != null && defaults.auth != consumer && (servesUsers || clientMounts != [ ]))
        {
          inherit consumer;
          provider = defaults.auth;
          kind = "authentication";
          phase = "session";
          required = servesUsers || builtins.any (mount: mount.required) clientMounts;
        }
    ) names)
    ++ map (
      {
        consumer,
        mountName,
        mount,
      }:
      {
        inherit consumer;
        inherit (mount) provider export required;
        kind = "mount";
        phase = "session";
        mount = mountName;
      }
    ) mounts
    ++ lib.mapAttrsToList (jobName: job: {
      consumer = job.scheduler;
      provider = job.target;
      kind = "job";
      phase = "run";
      required = true;
      job = jobName;
    }) (lib.filterAttrs (_: job: job.scheduler != job.target) jobs);
  manifest = {
    version = 1;
    inherit name defaults dependencies;
    jobs = lib.mapAttrs (jobName: job: {
      inherit (job)
        scheduler
        target
        schedule
        user
        keyPattern
        timeout
        ;
      command = "${tasks.${jobName}}/run";
    }) jobs;
    machines = lib.mapAttrs (machineName: machine: {
      inherit (machine) hostName machineId ip;
      system = toString systems.${machineName};
      roles =
        (lib.optional (serves machineName "auth") "auth")
        ++ (lib.optional (serves machineName "cpu") "cpu")
        ++ (lib.optional (serves machineName "fs") "file");
      endpoints = {
        auth = if serves machineName "auth" then endpoint machineName 567 else null;
        cpu = if serves machineName "cpu" then endpoint machineName 17019 else null;
        exports = builtins.mapAttrs (_: export: {
          address = endpoint machineName export.port;
          inherit (export) readOnly;
        }) configs.${machineName}.services.exports;
        tcp = lib.mapAttrs (port: _: endpoint machineName port) (
          configs.${machineName}.services.listen.tcp or { }
        );
      };
      mounts = lib.mapAttrs (
        mountName: mount:
        mount
        // lib.optionalAttrs (builtins.hasAttr mountName machine.mounts) {
          inherit (machine.mounts.${mountName}) provider export;
        }
      ) configs.${machineName}.namespace.mounts;
    }) machines;
  };
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
if names == [ ] then
  error "machines must not be empty"
else if !builtins.all label names then
  error "machine inventory keys must be lowercase labels of at most 63 characters"
else if !unique (map (machine: machine.machineId) (builtins.attrValues machines)) then
  error "duplicate machine identities"
else if !unique (map (machine: machine.hostName) (builtins.attrValues machines)) then
  error "duplicate hostnames"
else if !unique (map (machine: machine.ip) (builtins.attrValues machines)) then
  error "duplicate IPv4 addresses"
else if !builtins.all (provider: builtins.hasAttr provider machines) providerNames then
  error "discovery defaults refer to an unknown machine"
else if !builtins.all label (builtins.attrNames jobs) then
  error "job names must be lowercase labels of at most 63 characters"
else if
  !builtins.all (
    job: builtins.hasAttr job.scheduler machines && builtins.hasAttr job.target machines
  ) (builtins.attrValues jobs)
then
  error "a job refers to an unknown scheduler or target"
else if
  !builtins.all (
    job:
    serves job.scheduler "auth"
    && (
      job.scheduler == job.target
      || (
        serves job.target "cpu" && builtins.elem job.user configs.${job.target}.services.cpu.allowedUsers
      )
    )
  ) (builtins.attrValues jobs)
then
  error "jobs require an authentication scheduler and remote CPU access for their user"
else if !builtins.all (item: builtins.hasAttr item.mount.provider machines) mounts then
  error "a mount refers to an unknown provider"
else if !builtins.all (kind: serves defaults.${kind} kind) providers then
  error "a discovery provider does not enable its referenced role"
else if
  !builtins.all (
    item: builtins.hasAttr item.mount.export configs.${item.mount.provider}.services.exports
  ) mounts
then
  error "a mount refers to an unknown export"
else
  builtins.deepSeq ndb (
    builtins.deepSeq (map (machineName: systems.${machineName}.drvPath) names) {
      inherit systems discovery manifest;
      build = mkDerivation {
        name = "nix9-installation-${name}";
        buildCommand = ''
          mkdir -p $out/systems
          echo -n ${quote (builtins.toJSON manifest + "\n")} > $out/manifest.json
          echo -n ${quote ndb.database} > $out/ndb
          ${lib.concatMapStringsSep "\n" (machineName: ''
            echo ${quote (toString systems.${machineName})} > $out/systems/${machineName}
          '') names}
        '';
      };
    }
  )
