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
  phases = [ "installPhase" ];
  installPhase = ''
    fn copyRelease {
      mkdir -p $2
      @{
        cd $1
        # rc's * includes dotfiles.
        for(file in ./*) {
          if(test -d $file) copyRelease $file $2/$file
          if not if(test -e $file) cp $file $2/$file
        }
        status='''
      }
    }
    copyRelease $src $out
    fn copyRelease
    mkdir -p $out/bin
    ${builtins.concatStringsSep "\n" (
      map (command: "cp ${./bin + "/${command}"} $out/bin/${command}") [
        "nix-store"
        "nix-instantiate"
        "nix-build"
        "nix-build-remote"
        "nix-shell"
        "nix-profile"
        "nix9-rebuild"
        "nix9-deploy"
        "nix9-session"
        "webfs"
      ]
    )}
    echo 'nix9Next='$out > $out/activate
    cat $out/activate.rc >> $out/activate
    echo 'substituters = file://'$out'/cache?store=/usr/local/nix/store' > $out/nix.conf
    echo 'trusted-public-keys = '^`{cat $out/cache.pub} >> $out/nix.conf
    echo '!include /cfg/nix9/files/nix.conf' >> $out/nix.conf
  '';
}
