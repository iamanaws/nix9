{
  lib,
  services,
  mounts,
  binds,
  ndb,
  listenPorts,
  namespaceTools,
  cpuPackage,
  dialPackage,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  listener = label: port: "probe ${quote label} listener ${toString port}";
in
''
  healthAlarm=${namespaceTools}/bin/alarm
  healthMount=${namespaceTools}/bin/mount
  ${lib.optionalString (mounts != { }) "healthClient=${cpuPackage}/bin/tlsclient"}
  ${lib.optionalString (builtins.any (mount: mount.transport == "tcp") (builtins.attrValues mounts))
    ''
      healthDial=${dialPackage}/bin/dial
    ''
  }
  ${lib.optionalString (ndb != null) "healthNdb=${ndb.package}/bin/ndb/csquery"}
  fn healthChecks {
    ${lib.optionalString services.auth.enable ''
      ${listener "auth/listener" 567}
    ''}
    ${lib.optionalString services.cpu.enable (listener "cpu/listener" 17019)}
    ${lib.optionalString services.cwfs.enable (listener "cwfs/listener" services.cwfs.port)}
    ${lib.concatStringsSep "\n" (
      lib.mapAttrsToList (name: export: ''
        ${listener "export/${name}/listener" export.port}
        probe ${quote "export/${name}/directory"} directory ${quote export.path}
      '') services.exports
    )}
    ${lib.concatMapStringsSep "\n" (port: listener "tcp/${port}/listener" port) listenPorts}
    ${lib.optionalString (ndb != null) (
      lib.concatStringsSep "\n" (
        lib.mapAttrsToList (
          name: host:
          lib.concatMapStringsSep "\n" (hostName: ''
            probe ${quote "ndb/${hostName}"} ndb ${quote hostName} \
              ${lib.concatMapStringsSep " " quote (
                [ host.ip ] ++ map (address: address.ip) (host.extraAddresses or [ ])
              )}
          '') ([ name ] ++ (host.aliases or [ ]))
        ) (services.ndb.hosts or { })
      )
    )}
    ${lib.concatStringsSep "\n" (
      lib.mapAttrsToList (
        name: mount:
        let
          paths = lib.unique (
            map (binding: lib.removePrefix mount.mountPoint binding.source) (
              builtins.filter (binding: lib.hasPrefix (mount.mountPoint + "/") binding.source) binds
            )
          );
        in
        ''
          probe ${quote "mount/${name} ${mount.address}"} mount ${quote mount.transport} \
            ${quote mount.address} ${quote mount.keyPattern} ${quote mount.attach} \
            ${lib.concatMapStringsSep " " quote paths}
        ''
      ) mounts
    )}
    status='''
  }
  status='''
''
