{ mkDerivation }:
{
  name ? "user-environment",
  paths,
}:
let
  selected = builtins.foldl' (
    result: path: if builtins.elem path result then result else result ++ [ path ]
  ) [ ] (map (path: "${path}") paths);
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  pathList = builtins.concatStringsSep " " (map quote selected);
  bins = map (path: "${path}/bin") selected;
  binList = builtins.concatStringsSep " " (map quote bins);
  # The worker shares the caller's new namespace, but not its environment group.
  switch = ''
    rfork e
    path=(/$cputype/bin)
    for(package in (${pathList})) test -e $package
    for(package in $nix9EnvironmentPaths) {
      if(test -d $package/bin) /$cputype/bin/unmount $package/bin /bin
    }
    for(package in (${pathList})) {
      if(test -d $package/bin) /$cputype/bin/bind -b $package/bin /bin
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
        path=(${binList} $nix9BasePath)
        ${
          if selected == [ ] then
            ''
              PATH=$nix9BasePATH
              nix9EnvironmentActive=()
              nix9BasePath=()
              nix9BasePATH=()
            ''
          else
            ''
              PATH=${quote (builtins.concatStringsSep ":" bins)}
              if(! ~ $#nix9BasePATH 0) {
                if(! ~ $nix9BasePATH ''') PATH=$PATH^:^$nix9BasePATH
              }
              nix9EnvironmentActive=1
            ''
        }
        status='''
      }
    }
  '';
in
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
    echo ${quote activate} > $out/activate
  '';
}
