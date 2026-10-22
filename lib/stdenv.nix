{
  tools,
  shell ? "${tools}/bootstrap/rc/bin/rc",
  initialPath ? [ ],
  cc ? null,
  libc ? null,
  buildPlatform ? {
    system = "x86_64-plan9";
  },
  hostPlatform ? buildPlatform,
  setup ? null,
  prepareSource ? "",
  shellArgs ? [
    "-m"
    "${tools}/rcmain"
    "-e"
    "-c"
  ],
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
    buildPlatform
    hostPlatform
    ;
  initialPath = path;
  mkDerivation = import ./mk-derivation.nix {
    inherit
      tools
      shell
      cc
      libc
      buildPlatform
      hostPlatform
      setup
      prepareSource
      shellArgs
      ;
    initialPath = path;
  };
}
