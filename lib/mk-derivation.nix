{
  tools,
  initialPath ? [ ],
}:
let
  mkDerivation =
    attrs:
    let
      name = attrs.name or "${attrs.pname}-${attrs.version}";
      meta = attrs.meta or { };
      passthru = attrs.passthru or { };
      nativeBuildInputs = attrs.nativeBuildInputs or [ ];
      buildInputs = attrs.buildInputs or [ ];
      propagatedNativeBuildInputs = attrs.propagatedNativeBuildInputs or [ ];
      propagatedBuildInputs = attrs.propagatedBuildInputs or [ ];
      quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
      flags = values: builtins.concatStringsSep " " (map quote values);
      upperFirst =
        value:
        builtins.replaceStrings
          (builtins.genList (index: builtins.substring index 1 "abcdefghijklmnopqrstuvwxyz") 26)
          (builtins.genList (index: builtins.substring index 1 "ABCDEFGHIJKLMNOPQRSTUVWXYZ") 26)
          (builtins.substring 0 1 value)
        + builtins.substring 1 (builtins.stringLength value) value;
      phaseHooks =
        phase:
        let
          match = builtins.match "(.+)Phase" phase;
          stem = if match == null then phase else builtins.head match;
          suffix = upperFirst stem;
        in
        [
          "pre${suffix}"
          "post${suffix}"
        ];
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
      defaultPhases = [
        "unpackPhase"
        "buildPhase"
        "checkPhase"
        "installPhase"
      ];
      phases = attrs.phases or defaultPhases;
      phaseAttrs = defaultPhases ++ phases;
      defaults = {
        inherit unpackPhase buildPhase installPhase;
        checkPhase = "";
      };
      runPhase =
        phase:
        let
          hooks = phaseHooks phase;
          body = attrs.${phase} or (defaults.${phase} or (throw "unknown build phase '${phase}'"));
        in
        (
          if phase == "checkPhase" && !(attrs.doCheck or false) then
            ""
          else
            ''
              ${attrs.${builtins.elemAt hooks 0} or ""}
              ${body}${if phase == "unpackPhase" then "\ncd $sourceRoot" else ""}
              ${attrs.${builtins.elemAt hooks 1} or ""}
            ''
        )
        + (if phase == "checkPhase" then "\n" else "");
      script = attrs.buildCommand or (builtins.concatStringsSep "" (map runPhase phases));
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
      // builtins.removeAttrs attrs (
        [
          "name"
          "meta"
          "passthru"
          "sourceRoot"
          "nativeBuildInputs"
          "buildInputs"
          "propagatedNativeBuildInputs"
          "propagatedBuildInputs"
          "buildCommand"
          "phases"
          "doCheck"
          "makefile"
          "makeFlags"
          "buildFlags"
          "installFlags"
        ]
        ++ phaseAttrs
        ++ builtins.concatMap phaseHooks phaseAttrs
      )
    )
    // {
      inherit meta passthru;
      overrideAttrs =
        overrides:
        mkDerivation (attrs // (if builtins.isFunction overrides then overrides attrs else overrides));
    }
    // passthru;
in
mkDerivation
