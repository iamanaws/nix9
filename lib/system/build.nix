{
  mkDerivation,
  buildEnv,
  ndbPackage,
}:
{
  hostName,
  machineId ? null,
  packages ? [ ],
  files ? { },
  webfs ? { },
  networking ? { },
  logging ? { },
  services ? { },
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
    paths = packages ++ (if ndb == null then [ ] else [ ndb.package ]);
  };
  network = import ./network.nix {
    inherit hostName;
    configuration = networking;
  };
  serviceConfiguration =
    (
      {
        webfs ? { },
        timesync ? { },
        listen ? { },
        ndb ? { },
      }:
      {
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
      }
    )
      services;
  inherit (serviceConfiguration)
    managedWebfs
    timesync
    listen
    ndb
    ;
  logConfiguration = import ./logging.nix {
    configuration = logging;
    inherit mkDerivation;
    inherit (serviceConfiguration) timesyncLogging;
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
else
  builtins.deepSeq [ network timesync listen logConfiguration ndb ] (mkDerivation {
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
      ${if network == "" then "" else write "network" network}
      ${write "services/webfs.rc" (builtins.readFile ./webfs.rc)}
      ${write "services/reset.rc" (builtins.readFile ./reset.rc)}
      ${write "services/ndb.rc" (builtins.readFile ./ndb.rc)}
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
        if listen == null then
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
              '') (builtins.attrNames listen)
            )}
            echo 'rfork e' > $out/services/listen-check
            echo 'nix9ListenCheckSystem='$out >> $out/services/listen-check
            echo -n ${quote (builtins.readFile ./listen-check.rc)} >> $out/services/listen-check
            echo 'rfork e' > $out/services/listen-start
            echo 'nix9ListenStartSystem='$out >> $out/services/listen-start
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
      ${if logConfiguration == null then "" else write "logging" logConfiguration.prepare}
      ${if logConfiguration == null then "" else write "log-event" logConfiguration.event}
    '';
  })
