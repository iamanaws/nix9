{ mkDerivation }:
{
  name ? "user-environment",
  paths ? [ ],
  files ? { },
}:
let
  selected = builtins.foldl' (
    result: path: if builtins.elem path result then result else result ++ [ path ]
  ) [ ] (map (path: "${path}") paths);
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  pathList = builtins.concatStringsSep " " (map quote selected);
  bins = map (path: "${path}/bin") selected;
  binList = builtins.concatStringsSep " " (map quote bins);
  targets = builtins.attrNames files;
  targetList = builtins.concatStringsSep " " (map quote targets);
  validTarget =
    target:
    builtins.match "/([^/]+/)*[^/]+" target != null
    && builtins.all (part: part != "." && part != "..") (
      builtins.filter builtins.isString (builtins.split "/" target)
    );
  # The worker shares the caller's new namespace, but not its environment group.
  switch = ''
    rfork e
    path=(/$cputype/bin)
    for(package in (${pathList})) test -e $package
    for(target in (${targetList})) {
      test -f $target
      test -f $nix9NextEnvironment/files^$target
    }
    for(target in $nix9EnvironmentFileTargets) {
      /$cputype/bin/unmount $nix9EnvironmentFileRoot^$target $target
    }
    for(package in $nix9EnvironmentPaths) {
      if(test -d $package/bin) /$cputype/bin/unmount $package/bin /bin
    }
    for(package in (${pathList})) {
      if(test -d $package/bin) /$cputype/bin/bind -b $package/bin /bin
    }
    for(target in (${targetList})) {
      /$cputype/bin/bind $nix9NextEnvironment/files^$target $target
    }
    status='''
  '';
  activate = ''
    rfork ne && {
      if(~ $#nix9EnvironmentActive 0) {
        nix9BasePath=$path
        nix9BasePATH=$PATH
      }
      /$cputype/bin/rc -e -c ${quote switch} && {
        nix9EnvironmentPaths=(${pathList})
        nix9EnvironmentFileTargets=(${targetList})
        nix9EnvironmentFileRoot=${if targets == [ ] then "()" else "$nix9NextEnvironment/files"}
        nix9NextEnvironment=()
        path=(${binList} $nix9BasePath)
        PATH=$nix9BasePATH
        ${
          if selected == [ ] && targets == [ ] then
            ''
              nix9EnvironmentActive=()
              nix9BasePath=()
              nix9BasePATH=()
            ''
          else
            ''
              ${
                if selected == [ ] then
                  ""
                else
                  ''
                    PATH=${quote (builtins.concatStringsSep ":" bins)}
                    if(! ~ $#nix9BasePATH 0) {
                      if(! ~ $nix9BasePATH ''') PATH=$PATH^:^$nix9BasePATH
                    }
                  ''
              }
              nix9EnvironmentActive=1
            ''
        }
        status='''
      }
    }
  '';
in
assert builtins.all validTarget targets;
mkDerivation {
  inherit name;
  buildCommand = ''
    mkdir -p $out .commands
    for(package in (${pathList})) {
      if(test -d $package/bin) @{
        cd $package/bin
        for(command in * .[~.]* ..?*) {
          if(test -e $command) {
            if(test -e $TMPDIR/.commands/$command) {
              echo 'command collision:' $command `{cat $TMPDIR/.commands/$command} $package >[1=2]
              exit 'command collision'
            }
            echo $package > $TMPDIR/.commands/$command
          }
        }
        status='''
      }
    }
    ${builtins.concatStringsSep "\n" (
      map (target: ''
        mkdir -p $out/files^${quote (builtins.dirOf target)}
        echo -n ${quote files.${target}} > $out/files^${quote target}
      '') targets
    )}
    ${if targets == [ ] then "" else "echo 'nix9NextEnvironment='$out > $out/activate"}
    echo ${quote activate} >> $out/activate
  '';
}
