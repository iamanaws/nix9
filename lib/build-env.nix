{ mkDerivation }:
{
  name ? "user-environment",
  paths ? [ ],
  files ? { },
  namespace ? "",
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
    ifs=()
    fn environmentCommands {
      @{
        cd $1
        for(command in * .[~.]* ..?*) {
          if(test -d $command) {
            if(~ $3 bind) mkdir $2/$command
            environmentCommands $1/$command $2/$command $3 $4^$command^/
          }
          if not if(test -f $command) {
            source=`{cat $1/$command}
            if(~ $3 bind) {
              echo -n ''' > $2/$command
              /$cputype/bin/bind $source $2/$command
            }
            if not /$cputype/bin/unmount $source $2/$command
          }
        }
        if(! ~ $4 ''') {
          if(~ $3 bind) {
            for(base in /$cputype/bin /rc/bin)
              if(test -d $base/$4) /$cputype/bin/bind -a $base/$4 $2
          }
          # Remove the private union's self-binding as well as its native fallbacks.
          if not if(test -d /$cputype/bin/$4 || test -d /rc/bin/$4)
            /$cputype/bin/unmount $2
        }
        status='''
      }
    }
    for(package in (${pathList})) test -e $package
    for(target in (${targetList})) {
      test -f $target
      test -f $nix9NextEnvironment/files^$target
    }
    for(target in $nix9EnvironmentFileTargets) {
      /$cputype/bin/unmount $nix9EnvironmentFileRoot^$target $target
    }
    if(~ $#nix9EnvironmentCommandRoot 1) {
      environmentCommands $nix9EnvironmentCommandRoot/commands /bin unmount '''
      /$cputype/bin/unmount /bin /bin
    }
    if not {
      for(package in $nix9EnvironmentPaths) {
        if(test -d $package/bin) /$cputype/bin/unmount $package/bin /bin
      }
    }
    ${
      if selected == [ ] then
        ""
      else
        ''
          if(test -f $nix9NextEnvironment/merge-commands) {
            # Bind onto a private skeleton so the store remains unchanged.
            nextCommands=/tmp/nix9-environment-$pid
            mkdir $nextCommands
            /$cputype/bin/ramfs -m $nextCommands
            environmentCommands $nix9NextEnvironment/commands $nextCommands bind '''
            /$cputype/bin/bind -b $nextCommands /bin
            /$cputype/bin/unmount $nextCommands
            rm $nextCommands
          }
          if not {
            for(package in (${pathList})) {
              if(test -d $package/bin) /$cputype/bin/bind -b $package/bin /bin
            }
          }
        ''
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
        nix9EnvironmentCommandRoot=()
        if(test -f $nix9NextEnvironment/merge-commands)
          nix9EnvironmentCommandRoot=$nix9NextEnvironment
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
    mkdir -p $out/commands
    fn collectCommands {
      @{
        cd $1
        for(command in * .[~.]* ..?*) {
          if(test -e $command) {
            if(test -d $command) {
              if(test -f $2/$command) {
                echo 'command collision:' $3^$command >[1=2]
                exit 'command collision'
              }
              if(test -d $2/$command) echo -n ''' > $out/merge-commands
              mkdir -p $2/$command
              collectCommands $1/$command $2/$command $3^$command^/
            }
            if not {
              if(test -e $2/$command) {
                echo 'command collision:' $3^$command >[1=2]
                exit 'command collision'
              }
              echo -n $1/$command > $2/$command
            }
          }
        }
        status='''
      }
    }
    for(package in (${pathList})) {
      if(test -d $package/bin) collectCommands $package/bin $out/commands '''
    }
    ${builtins.concatStringsSep "\n" (
      map (target: ''
        mkdir -p $out/files^${quote (builtins.dirOf target)}
        echo -n ${quote files.${target}} > $out/files^${quote target}
      '') targets
    )}
    echo 'nix9NextEnvironment='$out > $out/activate
    echo ${quote activate} >> $out/activate
    echo ${quote ''
      #!/bin/rc -e
      rfork ne
    ''} > $out/session.rc
    echo '. '$out^'/activate' >> $out/session.rc
    echo ${quote ''
      ${namespace}
      if(~ $#* 0) exec /bin/rc -i
      if not exec $*
    ''} >> $out/session.rc
    echo '#!/bin/rc -e
    exec nix-build --run-session '^$out^' $*' > $out/session
    chmod +x $out/session $out/session.rc
  '';
}
