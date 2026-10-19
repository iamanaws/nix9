{
  packages,
  fail ? "",
  doCheck ? true,
  customUnpack ? false,
}:
let
  pkgs = import packages;
  stop =
    phase:
    if fail == phase then "echo phase-failure-${phase}; test -e /nix9-missing-phase-fixture" else "";
in
pkgs.mkDerivation (
  {
    pname = "phases";
    version = "1";
    src = ./phase-source;
    inherit doCheck;
    buildPhase = ''
      test -s trace
      echo patched > nested/.message
      test `{cat $src/nested/.message} '=' original
      ${stop "build"}
      echo build >> trace
      echo built > built
    '';
    checkPhase = ''
      test -s built
      ${stop "check"}
      echo check >> trace
    '';
    installPhase = ''
      test -s built
      ${stop "install"}
      echo install >> trace
      cp trace $out
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
)
