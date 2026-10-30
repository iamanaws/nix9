{
  lib,
  configuration,
  mounts,
  package,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  ancestor = parent: child: parent == child || lib.hasPrefix (parent + "/") child;
  make =
    name: backup:
    let
      error = message: throw "mkSystem: services.backups.${name}: ${message}";
      source = mounts.${backup.sourceMount};
      destination = mounts.${backup.destinationMount};
      tree = lib.foldl' (
        result: path: lib.recursiveUpdate result (lib.setAttrByPath (lib.splitString "/" path) { })
      ) { } backup.paths;
      proto =
        indent: tree:
        lib.concatStrings (
          lib.mapAttrsToList (
            name: children:
            "${indent}${name} - - -\n"
            + (if children == { } then "${indent}\t+ - - -\n" else proto (indent + "\t") children)
          ) tree
        );
    in
    if
      builtins.stringLength name > 63 || builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" name == null
    then
      error "name must be a lowercase label of at most 63 characters"
    else if !(mounts ? ${backup.sourceMount}) || !(mounts ? ${backup.destinationMount}) then
      error "sourceMount and destinationMount must name managed session mounts"
    else if source.transport != "tcp" || source.attach != "dump" then
      error "sourceMount must use native TCP with a dump attach"
    else if destination.transport != "tls" then
      error "destinationMount must use an authenticated TLS directory export"
    else if
      ancestor source.mountPoint destination.mountPoint
      || ancestor destination.mountPoint source.mountPoint
    then
      error "source and destination mount points must be separate"
    else if
      backup.paths == [ ]
      || builtins.any (
        path: builtins.length (builtins.filter (other: ancestor other path) backup.paths) != 1
      ) backup.paths
    then
      error "paths must be nonempty directories without duplicates or parent overlaps"
    else
      {
        inherit (backup) sourceMount destinationMount;
        prototype = proto "" tree;
        settings = ''
          backupName=${quote name}
          backupSourceName=${quote backup.sourceMount}
          backupDestinationName=${quote backup.destinationMount}
          backupSource=${quote source.mountPoint}
          backupDestination=${quote destination.mountPoint}
          backupPaths=(${lib.concatMapStringsSep " " quote backup.paths})
          backupTools=${package}
        '';
      };
in
lib.mapAttrs make configuration
