{
  tools,
  initialPath ? [ ],
}:
{
  inherit tools initialPath;
  mkDerivation = import ./mk-derivation.nix { inherit tools initialPath; };
}
