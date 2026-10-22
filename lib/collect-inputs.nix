{
  nativeBuildInputs,
  buildInputs,
  propagatedNativeBuildInputs ? [ ],
  propagatedBuildInputs ? [ ],
  initialPath ? [ ],
  libc ? null,
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  inputList = inputs: builtins.concatStringsSep " " (map quote inputs);
in
''
  nativeBuildInputs=( ${inputList (nativeBuildInputs ++ propagatedNativeBuildInputs)} )
  buildInputs=( ${
    inputList (buildInputs ++ propagatedBuildInputs ++ (if libc == null then [ ] else [ libc ]))
  } )
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
''
