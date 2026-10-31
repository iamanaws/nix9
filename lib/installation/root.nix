{
  lib,
  mkDerivation,
  name,
  configuration,
  machines,
  bootFiles,
  bootstrapNdb,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
mkDerivation {
  name = "nix9-root-${name}";
  buildCommand = ''
    mkdir -p $out/tree
    gunzip -c ${configuration.base}/root.tar.gz > root.tar
    @{ cd $out/tree && tar xf $TMPDIR/root.tar }
    grep -s '^\. /lib/namespace.local$' $out/tree/lib/namespace
    cp ${configuration.base}/base.json $out/base.json
    mkdir -p $out/tree/cfg/nix9/boot $out/tree/cfg/default/service $out/tree/sys/lib/tls/webfs
    echo '. /cfg/nix9/boot/$nix9machine/namespace' > $out/tree/lib/namespace.local
    version=`{echo $out | sed 's,.*/,,'}
    echo $version > $out/tree/cfg/nix9/root
    # Native newns expands only 27 bytes of an environment value.
    sed 's,\$rootdir,/root/systems/'^$version^',g' $out/tree/lib/namespace > namespace
    cp namespace $out/tree/lib/namespace
    ${lib.concatStringsSep "\n" (
      lib.mapAttrsToList (path: text: ''
        mkdir -p $out/tree/${builtins.dirOf path}
        echo -n ${quote text} > $out/tree/${path}
      '') configuration.files
    )}
    ${lib.optionalString (bootstrapNdb != "") ''
      cp $out/tree/lib/ndb/local ndb-local
      echo -n ${quote bootstrapNdb} > $out/tree/lib/ndb/local
      cat ndb-local >> $out/tree/lib/ndb/local
    ''}
    ${lib.concatMapStringsSep "\n" (
      machine:
      let
        files = bootFiles.${machine};
        directory = "$out/tree/cfg/nix9/boot/${machines.${machine}.machineId}";
      in
      ''
        mkdir -p ${directory}
        echo -n ${quote files.namespace} > ${directory}/namespace
        echo -n ${quote files.init} > ${directory}/init
        chmod 755 ${directory}/init
      ''
    ) (builtins.attrNames bootFiles)}
    cp ${./root-publish.rc} $out/publish
    cp ${./copy-tree.rc} $out/copy-tree.rc
    chmod 755 $out/publish
  '';
}
