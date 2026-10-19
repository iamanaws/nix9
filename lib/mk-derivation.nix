{
  tools,
  initialPath ? [ ],
}:
let
  mkDerivation =
    attrs:
    let
      name = attrs.name or "${attrs.pname}-${attrs.version}";
      nativeBuildInputs = attrs.nativeBuildInputs or [ ];
      buildInputs = attrs.buildInputs or [ ];
      propagatedNativeBuildInputs = attrs.propagatedNativeBuildInputs or [ ];
      propagatedBuildInputs = attrs.propagatedBuildInputs or [ ];
      quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
      flags = values: builtins.concatStringsSep " " (map quote values);
      propagate =
        file: inputs:
        if inputs == [ ] then
          ""
        else
          ''
            $tools/bin/mkdir -p $out/nix-support
            $tools/bin/echo ${flags inputs} > $out/nix-support/${file}
          '';

      makefile = attrs.makefile or "mkfile";
      makeFlags = flags (attrs.makeFlags or [ ]);
      mkPhase =
        commands:
        if attrs ? makefile || (attrs.makeFlags or [ ]) != [ ] then
          commands
        else
          ''
            if(test -f mkfile) {
              ${commands}
            }
            status='''
          '';
      buildPhase =
        attrs.buildPhase or (mkPhase ''
          mk -f ${quote makefile} ${makeFlags} ${flags (attrs.buildFlags or [ ])}
        '');
      installPhase =
        attrs.installPhase or (mkPhase ''
          mkdir -p $out/bin
          mk -f ${quote makefile} 'BIN='$out/bin ${makeFlags} ${flags (attrs.installFlags or [ ])} install
        '');
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
          ${attrs.preUnpack or ""}
          ${unpackPhase}
          cd $sourceRoot
          ${attrs.postUnpack or ""}
          ${attrs.preBuild or ""}
          ${buildPhase}
          ${attrs.postBuild or ""}
          ${
            if attrs.doCheck or false then
              ''
                ${attrs.preCheck or ""}
                ${attrs.checkPhase or ""}
                ${attrs.postCheck or ""}
              ''
            else
              ""
          }
          ${attrs.preInstall or ""}
          ${installPhase}
          ${attrs.postInstall or ""}
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
          propagatedNativeBuildInputs
          propagatedBuildInputs
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
            ${import ./setup-environment.nix {
              inherit
                nativeBuildInputs
                buildInputs
                propagatedNativeBuildInputs
                propagatedBuildInputs
                initialPath
                ;
            }}
            ${script}
            ${propagate "propagated-build-inputs" propagatedBuildInputs}
            ${propagate "propagated-native-build-inputs" propagatedNativeBuildInputs}
          ''
        ];
      }
      // builtins.removeAttrs attrs [
        "name"
        "sourceRoot"
        "nativeBuildInputs"
        "buildInputs"
        "propagatedNativeBuildInputs"
        "propagatedBuildInputs"
        "buildCommand"
        "unpackPhase"
        "buildPhase"
        "checkPhase"
        "installPhase"
        "doCheck"
        "makefile"
        "makeFlags"
        "buildFlags"
        "installFlags"
        "preUnpack"
        "postUnpack"
        "preBuild"
        "postBuild"
        "preCheck"
        "postCheck"
        "preInstall"
        "postInstall"
      ]
    )
    // {
      overrideAttrs =
        overrides:
        mkDerivation (attrs // (if builtins.isFunction overrides then overrides attrs else overrides));
    };
in
mkDerivation
