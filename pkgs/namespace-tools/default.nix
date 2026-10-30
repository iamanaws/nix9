{
  mkDerivation,
  src,
  libauth,
  libauthsrv,
}:
mkDerivation {
  name = "namespace-tools";
  inherit src;
  buildInputs = [
    libauth
    libauthsrv
  ];
  buildCommand = ''
    mkdir -p $out/bin
    for(command in mount alarm) {
      cp $src/sys/src/cmd/$command.c $command.c
      6c -o $command.6 $command.c
      6l -o $out/bin/$command $command.6
    }
    cp ${./bindings.c} bindings.c
    6c -o bindings.6 bindings.c
    6l -o $out/bin/nix9-bindings bindings.6
  '';
}
