{
  lib,
  exports,
  mounts,
  cpuPackage,
  exportfsPackage,
  namespaceTools,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  names = builtins.attrNames exports ++ builtins.attrNames mounts;
  validName =
    name:
    builtins.stringLength name <= 63 && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" name != null;
  ports = map (item: toString item.port) (builtins.attrValues exports);
  points = map (item: item.mountPoint) (builtins.attrValues mounts);
  overlaps = a: b: a == b || lib.hasPrefix (a + "/") b || lib.hasPrefix (b + "/") a;
  protected = [
    "/usr/local/nix"
    "/usr/local/pkg"
    "/cfg/nix9"
  ];
  error = message: throw "mkSystem: ${message}";
in
if !builtins.all validName names then
  error "export and mount names must be lowercase labels of at most 63 characters"
else if !builtins.all (item: item.allowedUsers != [ ]) (builtins.attrValues exports) then
  error "services.exports.allowedUsers must name at least one user"
else if builtins.length ports != builtins.length (lib.unique ports) then
  error "services.exports must use distinct TCP ports"
else if
  builtins.any (
    port:
    builtins.elem port [
      "567"
      "17019"
    ]
  ) ports
then
  error "services.exports must not use authentication or CPU ports 567 and 17019"
else if builtins.any (point: lib.hasPrefix "/mnt/nix9-" point) points then
  error "namespace.mounts must not cover internal /mnt/nix9- paths"
else if builtins.any (point: builtins.any (path: overlaps point path) protected) points then
  error "namespace.mounts must not cover the local Nix runtime, state or machine configuration"
else if
  builtins.any (
    name:
    builtins.any (
      other: name != other && overlaps mounts.${name}.mountPoint mounts.${other}.mountPoint
    ) (builtins.attrNames mounts)
  ) (builtins.attrNames mounts)
then
  error "namespace.mounts mount points must not overlap"
else
  {
    inherit exports;
    packages = lib.optionals (mounts != { }) [
      cpuPackage
      namespaceTools
    ];
    scripts = lib.mapAttrs' (
      name: item:
      lib.nameValuePair (toString item.port) ''
        #!/bin/rc
        fn serve {
          if(! ~ $user ${lib.concatMapStringsSep " " quote item.allowedUsers}) exit 'file access denied'
          exec ${exportfsPackage}/bin/exportfs ${lib.optionalString item.readOnly "-R "}-r ${quote item.path}
        }
        exec ${cpuPackage}/bin/tlssrv -a -k ${quote item.keyPattern} /bin/rc -c serve
      ''
    ) exports;
    configuration = ''
      nix9NamespaceCount=${toString (4 * builtins.length (builtins.attrNames mounts))}
      ${lib.optionalString (mounts != { }) ''
        nix9NamespaceTools=${namespaceTools}
        nix9NamespaceClient=${cpuPackage}/bin/tlsclient
      ''}
      fn configureMounts {
        ${lib.concatStringsSep "\n" (
          lib.mapAttrsToList (name: item: ''
            mountShare ${quote name} ${quote item.mountPoint} ${quote item.address} ${quote item.keyPattern} ${toString item.timeout} ${
              if item.required then "1" else "0"
            }
          '') mounts
        )}
      }
    '';
  }
