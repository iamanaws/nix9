{ mkDerivation, buildEnv }:
{
  hostName,
  packages ? [ ],
  files ? { },
  webfs ? { },
  networking ? { },
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
    paths = packages;
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
      }
    )
      services;
  inherit (serviceConfiguration) managedWebfs timesync;
  write = path: contents: ''
    mkdir -p $out/${builtins.dirOf path}
    echo -n ${quote contents} > $out/${path}
  '';
  hook = original: entry: ''
    # nix9 system hook v1
    if(test -r ${original}.nix9-original) . ${original}.nix9-original
    if(test -r /usr/local/nix/state/gcroots/system) {
      nix9BootSystem=`{cat /usr/local/nix/state/gcroots/system}
      . $nix9BootSystem/${entry}
      nix9BootSystem=()
    }
    status='''
  '';
in
if !validName hostName || builtins.stringLength hostName > 63 then
  throw "mkSystem: hostName must be a lowercase DNS label of at most 63 characters"
else if !validFiles then
  throw "mkSystem: files must map relative file paths without traversal or parent conflicts to text"
else if !validPins then
  throw "mkSystem: certificatePins must map lowercase DNS hosts to nonempty lists of SHA-256 hex fingerprints"
else if !builtins.isBool managedWebfs then
  throw "mkSystem: services.webfs.enable must be a boolean"
else
  builtins.deepSeq [ network timesync ] (mkDerivation {
    name = "nix9-system-${hostName}";
    buildCommand = ''
      mkdir -p $out/files $out/webfs/hosts $out/hooks $out/services
      echo nix9-system-1 > $out/system
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
      ${write "profile" (builtins.readFile ./profile.rc)}
      ${write "services/webfs.rc" (builtins.readFile ./webfs.rc)}
      ${if managedWebfs then write "services/webfs-enabled" "enabled\n" else ""}
      ${if timesync == "" then "" else write "services/timesync.rc" timesync}
      ${write "hooks/termrc.local" (hook "/rc/bin/termrc.local" "boot")}
      ${write "hooks/rcmain.local" (hook "/rc/lib/rcmain.local" "profile")}
    '';
  })
