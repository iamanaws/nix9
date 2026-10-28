{
  stdenv,
  go,
  goEnvironment,
}:
{
  subPackages ? [ "." ],
  vendor ? null,
  ldflags ? [ ],
  ...
}@attrs:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
in
stdenv.mkDerivation (
  builtins.removeAttrs attrs [
    "subPackages"
    "vendor"
    "ldflags"
  ]
  // {
    nativeBuildInputs = [ go ] ++ (attrs.nativeBuildInputs or [ ]);
    preBuild = goEnvironment + ''
      ${
        if vendor == null then
          ""
        else
          ''
            fn copyGoVendor {
              mkdir -p $2
              @{
                cd $1
                for(file in ./* ./.[~.]* ./..?*) {
                  if(test -d $file) copyGoVendor $file $2/$file
                  if not if(test -e $file) {
                    cp $file $2/$file
                    chmod u+w $2/$file
                  }
                }
                status='''
              }
            }
            copyGoVendor ${vendor} `{pwd}^/vendor
          ''
      }
      ${attrs.preBuild or ""}
    '';
    buildPhase =
      attrs.buildPhase or ''
        mkdir -p $TMPDIR/go-bin
        for(package in (${builtins.concatStringsSep " " (map quote subPackages)})) {
          go build '-mod=vendor' -trimpath '-buildvcs=false' -p 2 \
            ${quote ("-ldflags=" + builtins.concatStringsSep " " ([ "-buildid=" ] ++ ldflags))} \
            -o $TMPDIR/go-bin/ $package
        }
      '';
    doCheck = attrs.doCheck or true;
    checkPhase =
      attrs.checkPhase or ''
        go test '-mod=vendor' -p 2 -timeout 5m ./...
      '';
    installPhase =
      attrs.installPhase or ''
        mkdir -p $out/bin
        cp $TMPDIR/go-bin/* $out/bin/
      '';
  }
)
