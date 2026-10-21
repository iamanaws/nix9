{ packages }:
let
  pkgs = import packages;
  check = ''
    test `{sha1sum < /proc/$pid/text} '=' `{sha1sum < $rcBinary}
    test `{whatis rc} '=' $rcBinary
    echo native-rc-PASS
  '';
in
{
  rebuilt = pkgs.rc.override { inherit (pkgs) stdenv yacc; };
  program = pkgs.stdenv.mkDerivation {
    name = "rc-tests";
    nativeBuildInputs = [ pkgs.sha1sum ];
    rcBinary = "${pkgs.rc}/bin/rc";
    buildCommand = ''
      ${check}
      echo '#!/bin/rc
      exit seed-shell-unavailable' > blocked
      chmod +x blocked
      bind blocked $tools/bootstrap/rc/bin/rc
      rc -c 'echo nested-rc-PASS'
      echo passed > $out
    '';
  };
  shell = pkgs.mkShell {
    nativeBuildInputs = [ pkgs.sha1sum ];
    shellHook = ''
      rcBinary=${pkgs.rc}/bin/rc
      ${check}
      rcCheck=${builtins.toFile "check-rc" check}
    '';
  };
}
