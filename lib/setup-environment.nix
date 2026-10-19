{
  nativeBuildInputs,
  buildInputs,
  interactive ? false,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  inputList = inputs: builtins.concatStringsSep " " (map quote inputs);
  searchPath = map (input: "${input}/bin") nativeBuildInputs ++ [ "/bin" ];
  bindInputs =
    if interactive then
      builtins.foldl' (result: input: [ input ] ++ result) [ ] nativeBuildInputs
    else
      nativeBuildInputs;
in
''
  $tools/bin/bind $tools/sys/include /sys/include
  $tools/bin/bind $tools/amd64/include /amd64/include
  $tools/bin/bind $tools/amd64/lib /amd64/lib
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
    if($tools/bin/test -d $input/bin) $tools/bin/bind ${
      if interactive then "-b" else "-a"
    } $input/bin /bin
  }
  for(input in $buildInputs) {
    if($tools/bin/test -d $input/include) $tools/bin/bind -a $input/include /sys/include
    if($tools/bin/test -d $input/lib) $tools/bin/bind -a $input/lib /amd64/lib
    if($tools/bin/test -d $input/include/ape) $tools/bin/bind -a $input/include/ape /sys/include/ape
    if($tools/bin/test -d $input/lib/ape) $tools/bin/bind -a $input/lib/ape /amd64/lib/ape
  }
''
