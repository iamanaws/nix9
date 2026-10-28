let
  pkgs = import ./packages;
in
pkgs.stdenv.mkDerivation {
  name = "nix9-release";
  src = builtins.path {
    path = ./.;
    name = "nix9-source";
    filter =
      path: type:
      !(builtins.elem (toString path) (
        map (name: toString ./. + "/${name}") [
          "activate"
          "nix.conf"
          "bin"
        ]
      ));
  };
  phases = [
    "unpackPhase"
    "installPhase"
  ];
  installPhase = ''
    mkdir -p $out/bin
    ${builtins.concatStringsSep "\n" (
      map (command: "cp ${./bin + "/${command}"} $out/bin/${command}") [
        "nix-store"
        "nix-instantiate"
        "nix-build"
        "nix-shell"
        "nix-profile"
        "webfs"
      ]
    )}
    tar cf /fd/1 . | @{ cd $out; tar xf /fd/0 }
    echo 'nix9Next='$out > $out/activate
    cat activate.rc >> $out/activate
    echo 'substituters = file://'$out'/cache?store=/usr/local/nix/store' > $out/nix.conf
    echo 'trusted-public-keys = '^`{cat $out/cache.pub} >> $out/nix.conf
  '';
}
