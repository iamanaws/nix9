{
  packages,
  fail ? "",
  doCheck ? true,
  customUnpack ? false,
  hooks ? false,
  singleCommand ? false,
  phases ? null,
}:
let
  pkgs = import packages;
  stop =
    phase:
    if fail == phase then "echo phase-failure-${phase}; test -e /nix9-missing-phase-fixture" else "";
  hook =
    phase:
    if hooks then
      ''
        ${stop phase}
        echo ${phase} >> $TMPDIR/phase-order
      ''
    else
      "";
in
pkgs.mkDerivation (
  {
    pname = "phases";
    version = "1";
    src = ./phase-source;
    inherit doCheck;
    preUnpack = ''
      ${hook "preUnpack"}
      hookState=shared
    '';
    postUnpack = ''
      test $hookState '=' shared
      cat trace >> $TMPDIR/phase-order
      ${hook "postUnpack"}
    '';
    preBuild = hook "preBuild";
    postBuild = hook "postBuild";
    preGenerate = hook "preGenerate";
    postGenerate = hook "postGenerate";
    preCheck = hook "preCheck";
    postCheck = hook "postCheck";
    preInstall = hook "preInstall";
    postInstall =
      if hooks then
        ''
          ${stop "postInstall"}
          echo postInstall >> $out
        ''
      else
        "";
    buildPhase = ''
      test -s trace
      ${
        if phases != null && builtins.elem "generatePhase" phases then
          "test $generationState '=' shared"
        else
          ""
      }
      echo patched > nested/.message
      test `{cat $src/nested/.message} '=' original
      ${stop "build"}
      echo build >> $TMPDIR/phase-order
      echo built > built
    '';
    generatePhase = ''
      test -s trace
      test $hookState '=' shared
      ${stop "generate"}
      echo generate >> $TMPDIR/phase-order
      generationState=shared
      echo generated > built
    '';
    checkPhase = ''
      test -s built
      ${stop "check"}
      echo check >> $TMPDIR/phase-order
    '';
    installPhase = ''
      test -s built
      ${stop "install"}
      echo install >> $TMPDIR/phase-order
      cp $TMPDIR/phase-order $out
    '';
  }
  // (
    if customUnpack || fail == "unpack" then
      {
        unpackPhase = ''
          ${stop "unpack"}
          mkdir source source/nested
          echo original > source/nested/.message
          echo custom-unpack > source/trace
        '';
      }
    else
      { }
  )
  // (if singleCommand then { buildCommand = "echo single-command > $out"; } else { })
  // (if phases == null then { } else { inherit phases; })
)
