{
  tools,
  shell ? "${tools}/bin/rc",
  initialPath ? [ ],
  cc ? null,
  libc ? null,
}:
let
  path = initialPath ++ (if cc == null then [ ] else [ cc ]);
in
{
  inherit
    tools
    shell
    cc
    libc
    ;
  initialPath = path;
  mkDerivation = import ./mk-derivation.nix {
    inherit tools shell libc;
    initialPath = path;
  };
}
