{
  lib,
  programs,
  plumber,
  packages,
}:
let
  inherit (programs) rio acme;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] (toString value) + "'";
  arguments = words: lib.concatMapStringsSep " " quote words;
  acmeArguments = [
    "-c"
    (toString acme.columns)
    "-f"
    rio.font
    "-F"
    acme.fixedFont
  ]
  ++ lib.optionals (acme.files != [ ]) ([ "--" ] ++ acme.files);
  window =
    entry:
    "${packages.rio}/bin/window -m"
    + lib.optionalString (entry.directory != null) (" -cd " + quote entry.directory)
    + lib.optionalString (entry.rectangle != null) (" -r " + arguments entry.rectangle)
    + " "
    + arguments entry.command
    + "\n";
  windows =
    lib.optional acme.start {
      inherit (acme) directory rectangle;
      command = [ "${packages.acme}/bin/acme" ] ++ acmeArguments;
    }
    ++ rio.windows;
  directories = lib.unique (
    builtins.filter (directory: directory != null) (map (entry: entry.directory) windows)
  );
in
builtins.deepSeq [ programs plumber ] {
  packages =
    lib.optionals rio.enable [
      packages.rio
      packages.rc
    ]
    ++ lib.optional acme.enable packages.acme
    ++ lib.optional plumber.enable packages.plumber;
  # This file only configures the calling namespace and environment. The native
  # profile chooses whether and when to start plumber, Rio or Acme.
  profile = ''
    rioargs=()
    acmeargs=()
    plumberargs=()
    ${lib.optionalString (rio.enable || acme.enable) ''
      font=${quote rio.font}
      tabstop=${toString acme.tabStop}
      # Acme searches /bin directly when it launches commands.
      # Compare file identities: two releases can contain identical wrappers.
      fn nix9ProgramIdentity {
        if(/$cputype/bin/test -f $1)
          /$cputype/bin/ls -qld $1 >[2]/dev/null | /$cputype/bin/awk '{print $1 ":" $5 ":" $6}'
        status='''
      }
      nix9ProgramSource=`{nix9ProgramIdentity $nix9/bin/nix-build}
      nix9ProgramCurrent=`{nix9ProgramIdentity /bin/nix-build}
      if(! ~ $#nix9ProgramSource 1 || ! ~ $#nix9ProgramCurrent 1 || ! ~ $nix9ProgramSource $nix9ProgramCurrent)
        bind -b $nix9/bin /bin || exit 'cannot expose Nix commands'
      fn nix9ProgramIdentity
      nix9ProgramSource=()
      nix9ProgramCurrent=()
    ''}
    ${lib.optionalString rio.enable ''
      rioargs=(-f ${quote rio.font} ${lib.optionalString rio.scroll "-s"} -i $nix9System/programs/rio/riostart)
    ''}
    ${lib.optionalString acme.enable "acmeargs=(${arguments acmeArguments})"}
    ${lib.optionalString plumber.enable "plumberargs=(-p $nix9System/services/plumber/plumbing)"}
    status='''
  '';
  riostart = ''
    #!/bin/rc -e
    cd $home || exit 'cannot enter home directory'
    ${lib.concatMapStrings (directory: ''
      test -d ${quote directory} || {
        echo 'riostart: working directory is unavailable:' ${quote directory} >[1=2]
        exit 'directory unavailable'
      }
    '') directories}
    ${lib.concatMapStrings window windows}
    status='''
  '';
  rules = plumber.rules + "\n";
}
