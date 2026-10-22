{ pkgs }:
{
  python = pkgs.python3.withPackages (p: [ p.pexpect ]);
  testSupport =
    files:
    pkgs.lib.fileset.toSource {
      root = ./.;
      fileset = pkgs.lib.fileset.unions ([ ./guest.py ] ++ files);
    };
}
