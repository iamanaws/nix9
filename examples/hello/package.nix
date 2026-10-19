{ stdenv }:
stdenv.mkDerivation {
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
  doCheck = true;
  checkPhase = "./6.out";
}
