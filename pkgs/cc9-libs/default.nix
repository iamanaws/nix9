{ callPackage, cc9 }:
{
  compression = callPackage ./compression.nix { inherit cc9; };
  sodium = callPackage ./sodium.nix { inherit cc9; };
  sqlite = callPackage ./sqlite.nix { inherit cc9; };
  boost = callPackage ./boost.nix { inherit cc9; };
  digests = callPackage ./digests.nix { inherit cc9; };
}
