{
  nativeBuildInputs,
  buildInputs,
  propagatedNativeBuildInputs ? [ ],
  propagatedBuildInputs ? [ ],
  initialPath ? [ ],
  interactive ? false,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  inputList = inputs: builtins.concatStringsSep " " (map quote inputs);
in
''
  $tools/bin/bind $tools/sys/include /sys/include
  $tools/bin/bind $tools/amd64/include /amd64/include
  $tools/bin/bind $tools/amd64/lib /amd64/lib
  objtype=amd64
  $tools/bin/bind $tools/amd64/mkfile /amd64/mkfile
  $tools/bin/bind $tools/sys/src/mkfile.proto /sys/src/mkfile.proto
  for(file in mkone mklib mkmany mksyslib) {
    $tools/bin/bind $tools/sys/src/cmd/$file /sys/src/cmd/$file
  }
  nativeBuildInputs=( ${inputList (nativeBuildInputs ++ propagatedNativeBuildInputs)} )
  buildInputs=( ${inputList (buildInputs ++ propagatedBuildInputs)} )
  fn findInputs {
    inputType=$1
    pendingInputs=$*(2-)
    foundInputs=()
    while(! ~ $#pendingInputs 0) {
      input=$pendingInputs(1)
      pendingInputs=$pendingInputs(2-)
      if(! ~ $input $foundInputs) {
        foundInputs=($foundInputs $input)
        if($tools/bin/test -f $input/nix-support/propagated-build-inputs) {
          pendingInputs=($pendingInputs `{$tools/bin/cat $input/nix-support/propagated-build-inputs})
        }
        if($tools/bin/test -f $input/nix-support/propagated-native-build-inputs) {
          if(~ $inputType native) {
            pendingInputs=($pendingInputs `{$tools/bin/cat $input/nix-support/propagated-native-build-inputs})
          }
          if not nativeBuildInputs=($nativeBuildInputs `{$tools/bin/cat $input/nix-support/propagated-native-build-inputs})
        }
      }
    }
    status='''
  }
  findInputs build $buildInputs
  buildInputs=$foundInputs
  findInputs native $nativeBuildInputs ${inputList initialPath}
  nativeBuildInputs=$foundInputs
  fn findInputs
  buildPath=()
  bindInputs=()
  for(input in $nativeBuildInputs) {
    buildPath=($buildPath $input/bin)
    bindInputs=($input $bindInputs)
  }
  buildPath=($buildPath /bin)
  path=($buildPath ${if interactive then "$path" else ""})
  ${if interactive then "previousPATH=$PATH" else ""}
  PATH='''
  for(directory in $buildPath) {
    if(~ $PATH ''') PATH=$directory
    if not PATH=$PATH^:^$directory
  }
  ${
    if interactive then
      ''
        if(! ~ $#previousPATH 0) {
          if(! ~ $previousPATH ''') PATH=$PATH^:^$previousPATH
        }
      ''
    else
      ""
  }
  # APE execvp searches /bin, so commands also need namespace bindings.
  for(input in $bindInputs) {
    if($tools/bin/test -d $input/bin) $tools/bin/bind -b $input/bin /bin
  }
  for(input in $buildInputs) {
    if($tools/bin/test -d $input/include) $tools/bin/bind -a $input/include /sys/include
    if($tools/bin/test -d $input/lib) $tools/bin/bind -a $input/lib /amd64/lib
    if($tools/bin/test -d $input/include/ape) $tools/bin/bind -a $input/include/ape /sys/include/ape
    if($tools/bin/test -d $input/lib/ape) $tools/bin/bind -a $input/lib/ape /amd64/lib/ape
  }
''
