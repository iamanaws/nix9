{ tools }:
attrs:
let
  name = attrs.name or "${attrs.pname}-${attrs.version}";
  nativeBuildInputs = attrs.nativeBuildInputs or [ ];
  buildInputs = attrs.buildInputs or [ ];
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  inputList = inputs: builtins.concatStringsSep " " (map quote inputs);
  # APE execvp ignores PATH, so tools also need bindings in /bin below.
  searchPath = map (input: "${input}/bin") nativeBuildInputs ++ [ "/bin" ];
  sourceRoot = attrs.sourceRoot or (if attrs ? src then "source" else ".");
  unpackPhase =
    attrs.unpackPhase or (
      if attrs ? src then
        ''
          if(test -d $src) {
            fn copySource {
              mkdir $2
              @{
                cd $1
                for(file in ./* ./.[~.]* ./..?*) {
                  if(test -d $file) copySource $file $2/$file
                  if not if(test -e $file) {
                    cp $file $2/$file
                    chmod u+w $2/$file
                  }
                }
                status='''
              }
            }
            copySource $src $TMPDIR/source
          }
          if not {
            switch($src) {
            case *.tar.gz *.tgz
              gunzip -c $src > source.tar
              tar xf source.tar
            case *.tar
              tar xf $src
            case *
              echo 'unsupported source archive: '^$src >[1=2]
              exit 'unsupported source archive'
            }
          }
        ''
      else
        ""
    );
  script =
    attrs.buildCommand or ''
      ${unpackPhase}
      cd $sourceRoot
      ${attrs.buildPhase or ""}
      ${if attrs.doCheck or false then attrs.checkPhase or "" else ""}
      ${attrs.installPhase or ""}
    '';
in
derivation (
  {
    inherit
      name
      tools
      sourceRoot
      nativeBuildInputs
      buildInputs
      ;
    system = "x86_64-plan9";
    builder = "${tools}/bin/rc";
    args = [
      "-m"
      "${tools}/rcmain"
      "-e"
      "-c"
      ''
        rfork n
        $tools/bin/mkdir .nix-empty .nix-rc
        $tools/bin/cp $tools/rcmain .nix-rc/rcmain
        $tools/bin/bind $tools/bin /bin
        for(directory in /amd64/bin /rc/bin) /bin/bind .nix-empty $directory
        /bin/bind .nix-rc /rc/lib
        /bin/bind $tools/sys/include /sys/include
        /bin/bind $tools/amd64/include /amd64/include
        /bin/bind $tools/amd64/lib /amd64/lib
        nativeBuildInputs=( ${inputList nativeBuildInputs} )
        buildInputs=( ${inputList buildInputs} )
        path=( ${inputList searchPath} )
        PATH=${quote (builtins.concatStringsSep ":" searchPath)}
        for(input in $nativeBuildInputs) {
          if(test -d $input/bin) bind -a $input/bin /bin
        }
        for(input in $buildInputs) {
          if(test -d $input/include) bind -a $input/include /sys/include
          if(test -d $input/lib) bind -a $input/lib /amd64/lib
          if(test -d $input/include/ape) bind -a $input/include/ape /sys/include/ape
          if(test -d $input/lib/ape) bind -a $input/lib/ape /amd64/lib/ape
        }
        ${script}
      ''
    ];
  }
  // builtins.removeAttrs attrs [
    "name"
    "sourceRoot"
    "nativeBuildInputs"
    "buildInputs"
    "buildCommand"
    "unpackPhase"
    "buildPhase"
    "checkPhase"
    "installPhase"
    "doCheck"
  ]
)
