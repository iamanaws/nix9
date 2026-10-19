{
  nativeBuildInputs,
  buildInputs,
  initialPath ? [ ],
  interactive ? false,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  inputList = inputs: builtins.concatStringsSep " " (map quote inputs);
  searchPath = map (input: "${input}/bin") (nativeBuildInputs ++ initialPath) ++ [ "/bin" ];
  bindInputs = builtins.foldl' (result: input: [ input ] ++ result) [ ] (
    nativeBuildInputs ++ initialPath
  );
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
  nativeBuildInputs=( ${inputList nativeBuildInputs} )
  buildInputs=( ${inputList buildInputs} )
  path=( ${inputList searchPath} ${if interactive then "$path" else ""} )
  ${if interactive then "previousPATH=$PATH" else ""}
  PATH=${quote (builtins.concatStringsSep ":" searchPath)}
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
  for(input in (${inputList bindInputs})) {
    if($tools/bin/test -d $input/bin) $tools/bin/bind -b $input/bin /bin
  }
  for(input in $buildInputs) {
    if($tools/bin/test -d $input/include) $tools/bin/bind -a $input/include /sys/include
    if($tools/bin/test -d $input/lib) $tools/bin/bind -a $input/lib /amd64/lib
    if($tools/bin/test -d $input/include/ape) $tools/bin/bind -a $input/include/ape /sys/include/ape
    if($tools/bin/test -d $input/lib/ape) $tools/bin/bind -a $input/lib/ape /amd64/lib/ape
  }
''
