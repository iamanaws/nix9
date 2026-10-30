{
  mkDerivation,
  buildEnv,
  lib,
  ndbPackage,
  authPackage,
  cpuPackage,
  listenPackage,
  exportfsPackage,
  namespaceTools,
}:
{
  hostName,
  machineId ? null,
  packages ? [ ],
  files ? { },
  directories ? { },
  webfs ? { },
  networking ? { },
  logging ? { },
  services ? { },
  namespace ? {
    mounts = { };
    binds = [ ];
  },
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  validName =
    value: builtins.isString value && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" value != null;
  parts = value: builtins.filter builtins.isString (builtins.split "/" value);
  validFile =
    value:
    builtins.match "[a-zA-Z0-9_+.-]+(/[a-zA-Z0-9_+.-]+)*" value != null
    && builtins.all (part: part != "." && part != "..") (parts value);
  targets = builtins.attrNames files;
  parentOf =
    parent: child: builtins.substring 0 (builtins.stringLength parent + 1) child == parent + "/";
  validFiles = builtins.all (
    target:
    validFile target
    && builtins.isString files.${target}
    && builtins.all (other: !(parentOf target other)) targets
  ) targets;
  pins =
    (
      {
        certificatePins ? { },
      }:
      certificatePins
    )
      webfs;
  hosts = builtins.attrNames pins;
  validHost =
    host:
    builtins.stringLength host <= 253
    && builtins.all (label: validName label && builtins.stringLength label <= 63) (
      builtins.filter builtins.isString (builtins.split "\\." host)
    );
  validPins = builtins.all (
    host:
    validHost host
    && builtins.isList pins.${host}
    && pins.${host} != [ ]
    && builtins.all (
      pin: builtins.isString pin && builtins.match "[0-9a-fA-F]{64}" pin != null
    ) pins.${host}
  ) hosts;
  environment = buildEnv {
    name = "nix9-system-packages";
    paths =
      packages
      ++ (if ndb == null then [ ] else [ ndb.package ])
      ++ (if access == null then [ ] else access.packages)
      ++ sharing.packages;
  };
  network = import ./network.nix {
    inherit lib hostName;
    configuration = networking;
  };
  serviceConfiguration =
    (
      {
        webfs ? { },
        timesync ? { },
        listen ? { },
        ndb ? { },
        auth,
        cpu,
        exports,
        cron,
      }:
      {
        cron = import ./cron.nix {
          inherit
            lib
            mkDerivation
            buildEnv
            authPackage
            cpuPackage
            auth
            ;
          configuration = cron;
        };
        managedWebfs =
          (
            {
              enable ? false,
            }:
            enable
          )
            webfs;
        timesync = import ./timesync.nix { configuration = timesync; };
        timesyncLogging = timesync.logging or false;
        listen = import ./listen.nix { configuration = listen; };
        ndb = import ./ndb.nix {
          configuration = ndb;
          package = ndbPackage;
        };
        access = import ./access.nix {
          inherit
            lib
            auth
            cpu
            authPackage
            cpuPackage
            exportfsPackage
            ;
          exports = sharing.exports;
          cronKeyFile = if cron.enable then cron.keyFile else null;
        };
      }
    )
      services;
  inherit (serviceConfiguration)
    managedWebfs
    timesync
    listen
    ndb
    access
    cron
    ;
  listenScripts = if listen == null then { } else listen;
  sharing = import ./sharing.nix {
    inherit
      lib
      cpuPackage
      exportfsPackage
      namespaceTools
      ;
    exports = services.exports;
    mounts = namespace.mounts;
    binds = namespace.binds;
    inherit directories;
  };
  logConfiguration = import ./logging.nix {
    configuration = logging;
    inherit mkDerivation;
    inherit (serviceConfiguration) timesyncLogging;
  };
  directoryConfiguration = import ./directories.nix {
    inherit
      lib
      mkDerivation
      directories
      namespaceTools
      ;
    mounts = namespace.mounts;
  };
  write = path: contents: ''
    mkdir -p $out/${builtins.dirOf path}
    echo -n ${quote contents} > $out/${path}
  '';
in
if machineId != null && (!validName machineId || builtins.stringLength machineId > 63) then
  throw "mkSystem: machineId must be a lowercase label of at most 63 characters"
else if !validName hostName || builtins.stringLength hostName > 63 then
  throw "mkSystem: hostName must be a lowercase DNS label of at most 63 characters"
else if !validFiles then
  throw "mkSystem: files must map relative file paths without traversal or parent conflicts to text"
else if !validPins then
  throw "mkSystem: certificatePins must map lowercase DNS hosts to nonempty lists of SHA-256 hex fingerprints"
else if !builtins.isBool managedWebfs then
  throw "mkSystem: services.webfs.enable must be a boolean"
else if access != null && access.cpu.enable && listenScripts ? "17019" then
  throw "mkSystem: services.cpu owns TCP port 17019"
else if access != null && access.auth.enable && listenScripts ? "567" then
  throw "mkSystem: services.auth owns TCP port 567"
else if
  builtins.any (port: builtins.hasAttr port listenScripts) (builtins.attrNames sharing.scripts)
then
  throw "mkSystem: services.exports and services.listen must not share a TCP port"
else
  builtins.deepSeq
    [
      network
      timesync
      listen
      logConfiguration
      ndb
      access
      directoryConfiguration
      cron
    ]
    (mkDerivation {
      name = "nix9-system-${hostName}";
      buildCommand = ''
        mkdir -p $out/files $out/webfs/hosts $out/services
        echo nix9-system-2 > $out/system
        ${if machineId == null then "" else "echo ${quote machineId} > $out/machine-id"}
        echo ${quote hostName} > $out/hostName
        echo ${environment} > $out/environment
        ${builtins.concatStringsSep "\n" (map (target: write ("files/" + target) files.${target}) targets)}
        ${builtins.concatStringsSep "\n" (
          map (
            host:
            write ("webfs/hosts/" + host) (
              builtins.concatStringsSep "" (map (pin: "x509 sha256=${pin}\n") pins.${host})
            )
          ) hosts
        )}
        echo 'nix9NextSystem='$out > $out/activate
        echo -n ${quote (builtins.readFile ./activate.rc)} >> $out/activate
        ${write "boot" (builtins.readFile ./boot.rc)}
        ${if directoryConfiguration == null then "" else write "directories" directoryConfiguration.script}
        ${if network == "" then "" else write "network" network}
        ${write "services/webfs.rc" (builtins.readFile ./webfs.rc)}
        ${write "services/reset.rc" (builtins.readFile ./reset.rc)}
        ${write "services/ndb.rc" (builtins.readFile ./ndb.rc)}
        ${write "namespace/config" sharing.configuration}
        ${write "services/namespace-mounts" (builtins.readFile ./namespace-mounts.rc)}
        echo 'nix9NamespaceNext='$out > $out/services/namespace.rc
        echo -n ${quote (builtins.readFile ./namespace.rc)} >> $out/services/namespace.rc
        echo 'rfork e' > $out/services/namespace-check
        echo 'nix9SystemCheck=1' >> $out/services/namespace-check
        echo '. '$out'/services/namespace.rc' >> $out/services/namespace-check
        ${
          if ndb == null then
            ""
          else
            ''
              ${write "ndb/local" ndb.database}
              ${write "ndb/include" (builtins.concatStringsSep "\n" ndb.include + "\n")}
              mkdir -p $out/ndb/bin/ndb
              echo '#!/bin/rc' > $out/ndb/bin/ndb/cs
              echo 'exec ${ndb.package}/bin/ndb/cs -f /lib/ndb/local $*' >> $out/ndb/bin/ndb/cs
              echo '#!/bin/rc' > $out/ndb/bin/ndb/dns
              ${
                if ndb.dns.enable then
                  ''
                    echo 'nix9DnsArgs=()' >> $out/ndb/bin/ndb/dns
                    echo 'for(argument in $*) if(! ~ $argument -r) nix9DnsArgs=($nix9DnsArgs $argument)' >> $out/ndb/bin/ndb/dns
                    echo 'exec ${ndb.package}/bin/ndb/dns -f /lib/ndb/local ${
                      if ndb.dns.resolver then "-r " else ""
                    }$nix9DnsArgs' >> $out/ndb/bin/ndb/dns
                  ''
                else
                  ''
                    echo ${quote "exit ''"} >> $out/ndb/bin/ndb/dns
                  ''
              }
              chmod 755 $out/ndb/bin/ndb/*
              echo 'path=('$out'/ndb/bin $path)' > $out/ndb/boot.rc
            ''
        }
        ${if managedWebfs then write "services/webfs-enabled" "enabled\n" else ""}
        ${if timesync == "" then "" else write "services/timesync.rc" timesync}
        ${
          if listen == null && access == null then
            ""
          else
            ''
              mkdir -p $out/services/listen $out/services/listen-scripts $out/services/listen-bin/aux
              ${builtins.concatStringsSep "\n" (
                map (port: ''
                  ${write ("services/listen-scripts/tcp" + port) listen.${port}}
                  echo '#!/bin/rc -e' > $out/services/listen/tcp${port}
                  echo 'nix9ListenConnectionSystem='$out >> $out/services/listen/tcp${port}
                  echo -n ${quote (builtins.readFile ./listen-connection.rc)} >> $out/services/listen/tcp${port}
                  chmod 755 $out/services/listen/tcp${port}
                '') (builtins.attrNames listenScripts)
              )}
              ${lib.concatStringsSep "\n" (
                lib.mapAttrsToList (port: script: ''
                  ${write ("services/listen/tcp" + port) script}
                  chmod 755 $out/services/listen/tcp${port}
                '') sharing.scripts
              )}
              ${
                if access != null && access.cpu.enable then
                  ''
                    ${write "services/listen/tcp17019" access.cpuScript}
                    chmod 755 $out/services/listen/tcp17019
                  ''
                else
                  ""
              }
              echo 'rfork e' > $out/services/listen-check
              echo 'nix9ListenCheckSystem='$out >> $out/services/listen-check
              echo 'nix9ListenBinary=${listenPackage}/bin/aux/listen' >> $out/services/listen-check
              echo -n ${quote (builtins.readFile ./listen-check.rc)} >> $out/services/listen-check
              echo 'rfork e' > $out/services/listen-start
              echo 'nix9ListenStartSystem='$out >> $out/services/listen-start
              echo 'nix9ListenBinary=${listenPackage}/bin/aux/listen' >> $out/services/listen-start
              echo -n ${quote (builtins.readFile ./listen-start.rc)} >> $out/services/listen-start
              echo '#!/bin/rc' > $out/services/listen-bin/aux/listen
              echo 'exec /$cputype/bin/rc '$out'/services/listen-start $*' >> $out/services/listen-bin/aux/listen
              chmod 755 $out/services/listen-bin/aux/listen
              echo 'mount -C #s$srvspec/boot /root $rootspec' > $out/services/listen.namespace
              echo '. $rootdir/lib/namespace' >> $out/services/listen.namespace
              echo 'bind -b '$out'/services/listen $nix9ListenDirectory' >> $out/services/listen.namespace
              echo 'nix9ListenRuntime=$nix9' > $out/services/listen-boot.rc
              echo 'path=('$out'/services/listen-bin $path)' >> $out/services/listen-boot.rc
            ''
        }
        ${
          if access == null then
            ""
          else
            ''
              ${write "services/access-config" access.settings}
              ${write "services/access-start" (builtins.readFile ./access-start.rc)}
              echo 'rfork e' > $out/services/access-check
              echo 'nix9AccessSystem='$out >> $out/services/access-check
              echo ${
                quote (
                  "nix9PlannedDirectories=("
                  + lib.concatMapStringsSep " " quote (builtins.attrNames directories)
                  + ")"
                )
              } >> $out/services/access-check
              echo -n ${quote (builtins.readFile ./access-check.rc)} >> $out/services/access-check
              ${
                if access.auth.enable then
                  ''
                    ${write "services/auth-policy" ("# Nix9 authentication delegation.\n" + access.policy)}
                    ${write "services/auth/tcp567" ''
                      #!/bin/rc
                      exec ${authPackage}/bin/auth/authsrv -N $3
                    ''}
                    chmod 755 $out/services/auth/tcp567
                    mkdir -p $out/services/listen-bin/auth
                    # cpurc's default keyfs invocation is replaced by the managed listener.
                    ${write "services/listen-bin/auth/keyfs" ''
                      #!/bin/rc
                      if(~ $#* 4 && ~ $1 -wp && ~ $2 -m && ~ $3 /mnt/keys && ~ $4 /adm/keys) exit '''
                      exec ${authPackage}/bin/auth/keyfs $*
                    ''}
                    chmod 755 $out/services/listen-bin/auth/keyfs
                  ''
                else
                  ""
              }
            ''
        }
        ${
          if cron == null then
            ""
          else
            ''
              mkdir -p $out/services/cron/tables $out/services/cron/commands
              ${lib.concatStringsSep "\n" (
                lib.mapAttrsToList (
                  name: task: write ("services/cron/commands/" + name) (toString task + "\n")
                ) cron.tasks
              )}
              ${lib.concatStringsSep "\n" (
                lib.mapAttrsToList (user: table: write ("services/cron/tables/" + user) table) cron.tables
              )}
              ${write "services/cron/start" cron.start}
            ''
        }
        ${if logConfiguration == null then "" else write "logging" logConfiguration.prepare}
        ${if logConfiguration == null then "" else write "log-event" logConfiguration.event}
      '';
    })
