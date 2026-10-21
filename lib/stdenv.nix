{
  tools,
  initialPath ? [ ],
  cc ? null,
  libc ? null,
}:
let
  path = initialPath ++ (if cc == null then [ ] else [ cc ]);
in
{
  inherit tools cc libc;
  initialPath = path;
  mkDerivation = import ./mk-derivation.nix {
    inherit tools libc;
    initialPath = path;
  };
}
