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
    roots
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
  bootNames = builtins.filter (name: machines.${name}.boot != null) names;
  networkRoots = lib.genAttrs bootNames (
    machineName:
    import ./netroot.nix {
      inherit lib mkDerivation;
      machine = machines.${machineName};
      provider = machines.${machines.${machineName}.boot.provider};
      authentication = machines.${defaults.auth};
      networking = configs.${machineName}.networking;
      # The CPU uses a published CWFS path; it does not need the root bundle in its store.
      rootDirectory =
        builtins.unsafeDiscardStringContext
          rootDirectories.${machines.${machineName}.boot.root};
    }
  );
  boot = builtins.mapAttrs (_: root: root.build) networkRoots;
  rootTrees = lib.mapAttrs (
    rootName: configuration:
    import ./root.nix {
      inherit lib mkDerivation machines;
      name = rootName;
      inherit configuration;
      bootFiles = networkRoots;
      bootstrapNdb = lib.optionalString (defaults.auth != null && defaults.authdom != null) (
        "authdom=${defaults.authdom} auth=${machines.${defaults.auth}.ip}\n\n"
      );
    }
  ) roots;
  rootDirectories = builtins.mapAttrs (
    _: root: "/systems/${builtins.baseNameOf (toString root)}"
  ) rootTrees;
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
      address = endpoint mount.provider (
        if mount.fileSystem == null then
          configs.${mount.provider}.services.exports.${mount.export}.port
        else
          configs.${mount.provider}.services.cwfs.port
      );
      transport = if mount.fileSystem == null then "tls" else "tcp";
      attach = if mount.fileSystem == null then "" else mount.fileSystem;
    }) machine.mounts
  ) machines;
  builderConfigurations = lib.mapAttrs (
    _: machine:
    lib.mapAttrs (
      provider: builder: builder // { host = machines.${provider}.hostName; }
    ) machine.builders
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
        nix.builders = builderConfigurations.${machineName};
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
              provider:
              configs.${machineName}.nix.builders.${provider} == builderConfigurations.${machineName}.${provider}
            ) (builtins.attrNames machine.builders);
            message = "installation inventory owns named builders for ${machineName}";
          }
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
      configs.${provider}.services.exports != { } || configs.${provider}.services.cwfs.enable
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
  deployment = lib.mapAttrs (machineName: machine: {
    inherit (machine.deployment) user keyPattern timeout;
    host = if machine.deployment.host == null then machine.ip else machine.deployment.host;
    remote = serves machineName "cpu" || machine.deployment.host != null;
  }) machines;
  dependencies =
    (lib.concatMap (
      consumer:
      let
        clientMounts = builtins.attrValues configs.${consumer}.namespace.mounts;
        servesUsers = serves consumer "cpu" || serves consumer "fs";
        hasBuilders = configs.${consumer}.nix.builders != { };
      in
      lib.optional
        (
          defaults.auth != null
          && defaults.auth != consumer
          && (servesUsers || clientMounts != [ ] || hasBuilders)
        )
        {
          inherit consumer;
          provider = defaults.auth;
          kind = "authentication";
          phase = if servesUsers || clientMounts != [ ] then "session" else "build";
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
        inherit (mount) provider required;
        kind = "mount";
        phase = "session";
        mount = mountName;
      }
      // (
        if mount.fileSystem == null then { inherit (mount) export; } else { inherit (mount) fileSystem; }
      )
    ) mounts
    ++ lib.mapAttrsToList (jobName: job: {
      consumer = job.scheduler;
      provider = job.target;
      kind = "job";
      phase = "run";
      required = true;
      job = jobName;
    }) (lib.filterAttrs (_: job: job.scheduler != job.target) jobs)
    ++ lib.concatMap (
      consumer:
      map (provider: {
        inherit consumer provider;
        kind = "builder";
        phase = "build";
        required = false;
      }) (builtins.attrNames machines.${consumer}.builders)
    ) names;
  bootDependencies = lib.concatMap (
    consumer:
    map
      (relationship: {
        inherit consumer;
        inherit (relationship) provider kind;
        phase = "boot";
        required = true;
      })
      [
        {
          provider = machines.${consumer}.boot.provider;
          kind = "root";
        }
        {
          provider = defaults.auth;
          kind = "authentication";
        }
      ]
  ) bootNames;
  manifest = {
    version = 1;
    inherit name defaults;
    roots = lib.mapAttrs (rootName: root: {
      directory = rootDirectories.${rootName};
      bundle = toString root;
      base = toString roots.${rootName}.base;
    }) rootTrees;
    dependencies = dependencies ++ bootDependencies;
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
      deployment = deployment.${machineName};
      builders = configs.${machineName}.nix.builders;
      boot =
        if machine.boot == null then
          null
        else
          machine.boot
          // {
            rootDirectory = rootDirectories.${machine.boot.root};
            files = toString boot.${machineName};
            address = "tcp!${machines.${machine.boot.provider}.ip}!564";
            auth = machines.${defaults.auth}.ip;
            attach = "main";
          };
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
        cwfs =
          if configs.${machineName}.services.cwfs.enable then
            {
              address = endpoint machineName configs.${machineName}.services.cwfs.port;
              transport = "tcp";
              fileSystems = [
                "main"
                "dump"
              ];
            }
          else
            null;
        tcp = lib.mapAttrs (port: _: endpoint machineName port) (
          configs.${machineName}.services.listen.tcp or { }
        );
      };
      mounts = lib.mapAttrs (
        mountName: mount:
        mount
        // lib.optionalAttrs (builtins.hasAttr mountName machine.mounts) (
          {
            inherit (machine.mounts.${mountName}) provider;
          }
          // (
            if machine.mounts.${mountName}.fileSystem == null then
              { inherit (machine.mounts.${mountName}) export; }
            else
              { inherit (machine.mounts.${mountName}) fileSystem; }
          )
        )
      ) configs.${machineName}.namespace.mounts;
    }) machines;
  };
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  deploymentScript = ''
    installationName=${quote name}
    machineNames=(${lib.concatMapStringsSep " " quote names})
    cpuClient=${packages.rcpu}/bin/rcpu
    fn machine {
      switch($1) {
      ${lib.concatMapStringsSep "\n" (
        machineName:
        let
          machine = machines.${machineName};
          connection = deployment.${machineName};
        in
        ''
          case ${quote machineName}
            identity=${quote machine.machineId}
            system=${quote (toString systems.${machineName})}
            remote=${if connection.remote then "1" else "0"}
            host=${quote connection.host}
            loginUser=(${lib.optionalString (connection.user != null) (quote connection.user)})
            keyPattern=${quote connection.keyPattern}
            timeout=${toString connection.timeout}
            jobTargets=(${
              lib.concatMapStringsSep " " quote (
                lib.unique (
                  map (job: job.target) (
                    builtins.attrValues (
                      lib.filterAttrs (_: job: job.scheduler == machineName && job.target != machineName) jobs
                    )
                  )
                )
              )
            })
        ''
      ) names}
      }
      status='''
    }
    status='''
  '';
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
else if
  !builtins.all (
    machineName:
    let
      user = machines.${machineName}.deployment.user;
    in
    user == null
    || !serves machineName "cpu"
    || builtins.elem user configs.${machineName}.services.cpu.allowedUsers
  ) names
then
  error "deployment user must be allowed by the machine's CPU service"
else if !builtins.all (provider: builtins.hasAttr provider machines) providerNames then
  error "discovery defaults refer to an unknown machine"
else if
  !builtins.all (
    machine:
    builtins.all (provider: builtins.hasAttr provider machines) (builtins.attrNames machine.builders)
  ) (builtins.attrValues machines)
then
  error "a builder refers to an unknown machine"
else if
  !builtins.all (
    machine:
    builtins.all (
      provider:
      serves provider "cpu"
      && (
        machine.builders.${provider}.user == null
        || builtins.elem machine.builders.${provider}.user configs.${provider}.services.cpu.allowedUsers
      )
    ) (builtins.attrNames machine.builders)
  ) (builtins.attrValues machines)
then
  error "builders require CPU access for their user"
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
    item:
    if item.mount.fileSystem == null then
      builtins.hasAttr item.mount.export configs.${item.mount.provider}.services.exports
    else
      configs.${item.mount.provider}.services.cwfs.enable
  ) mounts
then
  error "a mount refers to an unknown export or disabled filesystem provider"
else if !builtins.all label (builtins.attrNames roots) then
  error "root names must be lowercase labels of at most 63 characters"
else if
  !builtins.all (
    root:
    let
      paths = builtins.attrNames root.files;
      valid =
        path:
        builtins.match "[a-zA-Z0-9_+.-]+(/[a-zA-Z0-9_+.-]+)*" path != null
        && builtins.all (part: part != "." && part != "..") (lib.splitString "/" path)
        && !(path == "lib/namespace" || path == "lib/namespace.local" || lib.hasPrefix "cfg/nix9" path);
    in
    builtins.all valid paths
    && builtins.all (
      path: builtins.all (other: path == other || !lib.hasPrefix (path + "/") other) paths
    ) paths
  ) (builtins.attrValues roots)
then
  error "root files require non-overlapping relative paths outside managed boot hooks"
else if !builtins.all (name: builtins.hasAttr machines.${name}.boot.root roots) bootNames then
  error "a boot root refers to an unknown root tree"
else if !builtins.all (name: builtins.stringLength machines.${name}.machineId <= 27) bootNames then
  error "network-root machine identities must fit native namespace expansion (27 characters)"
else if
  !builtins.all (name: builtins.hasAttr machines.${name}.boot.provider machines) bootNames
then
  error "a boot root refers to an unknown provider"
else if
  !builtins.all (
    name:
    let
      provider = machines.${name}.boot.provider;
    in
    provider != name
    && configs.${provider}.services.cwfs.enable
    && configs.${provider}.services.cwfs.port == 564
    && machines.${provider}.boot == null
  ) bootNames
then
  error "boot roots require an independently booted CWFS provider on port 564"
else if
  bootNames != [ ]
  && (defaults.auth == null || defaults.authdom == null || machines.${defaults.auth}.boot != null)
then
  error "network-root boot requires an authentication domain and an independently booted authentication default"
else if !builtins.all (name: serves name "cpu") bootNames then
  error "network-root machines must enable CPU access"
else if
  !builtins.all (
    name:
    let
      network = configs.${name}.networking;
      primary = network.interfaces.${network.primaryInterface} or null;
    in
    network.enable
    && primary != null
    && !primary.useDHCP
    && primary.address == machines.${name}.ip
    && primary.prefixLength != null
  ) bootNames
then
  error "network-root boot requires a static primary interface matching the inventory IP"
else if
  !builtins.all (
    name:
    let
      current = machines.${name}.boot;
      overlaps = a: b: a == b || lib.hasPrefix (a + "/") b || lib.hasPrefix (b + "/") a;
    in
    builtins.all (
      other:
      let
        peer = machines.${other}.boot;
      in
      current.provider != peer.provider
      || (
        !overlaps current.stateDirectory rootDirectories.${peer.root}
        && (name == other || !overlaps current.stateDirectory peer.stateDirectory)
      )
    ) bootNames
  ) bootNames
then
  error "network-root machine state must not overlap a root tree or another machine's state"
else
  builtins.deepSeq [ ndb deployment ] (
    builtins.deepSeq (map (machineName: systems.${machineName}.drvPath) names) {
      inherit
        systems
        discovery
        manifest
        boot
        ;
      roots = rootTrees;
      build = mkDerivation {
        name = "nix9-installation-${name}";
        buildCommand = ''
          mkdir -p $out/systems $out/boot $out/roots
          echo -n ${quote (builtins.toJSON manifest + "\n")} > $out/manifest.json
          echo -n ${quote ndb.database} > $out/ndb
          echo -n ${quote deploymentScript} > $out/deployment.rc
          ${lib.concatMapStringsSep "\n" (machineName: ''
            echo ${quote (toString systems.${machineName})} > $out/systems/${machineName}
          '') names}
          ${lib.concatMapStringsSep "\n" (machineName: ''
            mkdir -p $out/boot/${machineName}
            cp ${boot.${machineName}}/* $out/boot/${machineName}/
            echo ${quote (toString boot.${machineName})} > $out/boot/${machineName}/path
          '') bootNames}
          ${lib.concatMapStringsSep "\n" (rootName: ''
            echo ${quote (toString rootTrees.${rootName})} > $out/roots/${rootName}
          '') (builtins.attrNames roots)}
        '';
      };
    }
  )
