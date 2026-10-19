{
  pkgs ? import /usr/local/pkg/native-packages,
}:
pkgs.stdenv.mkDerivation {
  name = "hello";
  src = builtins.path {
    path = ./.;
    name = "hello-source";
    filter =
      path: type:
      builtins.elem (builtins.baseNameOf path) [
        "hello.c"
        "mkfile"
      ];
  };
  buildPhase = "mk";
  doCheck = true;
  checkPhase = "./6.out";
  installPhase = ''
    mkdir -p $out/bin
    mk install 'BIN='$out/bin
  '';
}
