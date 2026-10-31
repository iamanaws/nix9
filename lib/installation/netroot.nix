{
  lib,
  mkDerivation,
  machine,
  provider,
  authentication,
  networking,
  rootDirectory,
}:
let
  inherit (machine.boot) stateDirectory;
  interface = networking.interfaces.${networking.primaryInterface};
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  state = "/root${stateDirectory}";
  bootargs =
    "tcp ether /net/${networking.primaryInterface} ${machine.ip} /${toString interface.prefixLength}"
    + lib.optionalString (networking.defaultGateway != null) " ${networking.defaultGateway}";
  settings = ''
    service=cpu
    sysname=${machine.hostName}
    nix9machine=${machine.machineId}
    bootargs=${bootargs}
    nobootprompt=${bootargs}
    fs=${provider.ip}
    auth=${authentication.ip}
    rootspec=main
    rootdir=/root${rootDirectory}
    init=/cfg/nix9/boot/${machine.machineId}/init
  '';
  namespace = ''
    bind -c ${state}/usr /usr
    bind -bc ${state}/cfg/nix9 /cfg/nix9
    bind -c ${state}/sys/lib/tls/webfs /sys/lib/tls/webfs
    bind -bc ${state}/rc/bin /rc/bin
    bind -bc ${state}/rc/lib /rc/lib
    bind -a /rc/bin /bin
    bind -bc ${state}/adm /adm
    bind -c ${state}/service /cfg/default/service
    bind -c ${state}/sys/log /sys/log
    bind -c ${state}/tmp /tmp
  '';
  init = ''
    #!/amd64/bin/rc
    path=(/amd64/bin /rc/bin)
    rfork ne
    fn fail {
      echo 'nix9: network root:' $* >[1=2]
      exit 'network root setup failed'
    }
    test -r ${state}/usr/local/nix/state/machine-id || fail 'machine state is not prepared'
    identity=`{cat ${state}/usr/local/nix/state/machine-id}
    ~ $#identity 1 && ~ $identity ${quote machine.machineId} || fail 'machine identity mismatch'
    test -r ${state}/usr/local/pkg/nix9/activate || fail 'Nix bootstrap is missing'
    for(directory in store state log)
      test -d ${state}/usr/local/nix/$directory || fail 'Nix directory is missing:' $directory
    nix9machine=${machine.machineId}
    nix9local=()
    exec /amd64/init -c
  '';
  configuration = ''
    machineId=${quote machine.machineId}
    rootDirectory=${quote rootDirectory}
    rootVersion=${quote (builtins.baseNameOf rootDirectory)}
    stateDirectory=${quote stateDirectory}
  '';
in
{
  inherit settings namespace init;
  build = mkDerivation {
    name = "nix9-netroot-${machine.machineId}";
    buildCommand = ''
      mkdir -p $out
      echo -n ${quote settings} > $out/plan9.ini
      echo -n ${quote namespace} > $out/namespace
      echo -n ${quote init} > $out/init
      echo -n ${quote configuration} > $out/configuration.rc
      cp ${./netroot-prepare.rc} $out/prepare
      cp ${./netroot-select.rc} $out/select
      cp ${./netroot-check.rc} $out/check-root.rc
      cp ${./copy-tree.rc} $out/copy-tree.rc
      chmod 755 $out/init $out/prepare $out/select
    '';
  };
}
