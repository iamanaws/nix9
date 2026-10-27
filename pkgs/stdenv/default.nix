{
  pkgs,
  cTools,
  sysroot,
  libc ? null,
  imageTools,
  ccSource,
}:
let
  plan9 = "${pkgs.plan9port}/plan9";
  shell = "${plan9}/bin/rc";
  pcc = pkgs.callPackage ./pcc.nix { source = ccSource; };
  cc = pkgs.callPackage ./cc-wrapper.nix {
    inherit
      cTools
      sysroot
      shell
      pcc
      ;
  };
  commands = pkgs.runCommand "cross-build-tools" { } ''
    mkdir -p "$out/bin"
    ln -s ${shell} "$out/bin/rc"
    for command in sed awk tr ls; do
      ln -s ${plan9}/bin/$command "$out/bin/$command"
    done
    cat > "$out/bin/mk" <<'EOF'
    #!${shell}
    FORCERCFORMK=1
    exec ${plan9}/bin/mk $*
    EOF
    chmod +x "$out/bin/mk"
  '';
  tools = pkgs.buildEnv {
    name = "cross-build-environment";
    paths = with pkgs; [
      coreutils
      gnugrep
      findutils
      gzip
      gnutar
      patch
      ed
      (lib.hiPrio commands)
    ];
  };
  initialPath = [
    cc
    tools
  ];
  setup =
    {
      interactive ? false,
      ...
    }@inputs:
    ''
      PLAN9=${plan9}
      ${pkgs.lib.optionalString (!interactive) "HOME=$TMPDIR"}
      NIX9_SED=${pkgs.gnused}/bin/sed
      NIX9_SHELL=${shell}
      objtype=amd64
      NIX9_ROOT=$TMPDIR/.nix-root
      ccroot=$NIX9_ROOT
      ${tools}/bin/mkdir -p $NIX9_ROOT/sys $NIX9_ROOT/amd64/lib
      ${tools}/bin/cp -r ${sysroot}/sys/include $NIX9_ROOT/sys/
      ${tools}/bin/cp -r ${sysroot}/amd64/include $NIX9_ROOT/amd64/
      ${tools}/bin/cp -r ${imageTools}/sys/src $NIX9_ROOT/sys/
      ${tools}/bin/cp ${imageTools}/amd64/mkfile $NIX9_ROOT/amd64/
      ${tools}/bin/chmod -R u+w $NIX9_ROOT
      ${import ../../lib/collect-inputs.nix (
        (builtins.removeAttrs inputs [ "interactive" ]) // { inherit initialPath libc; }
      )}
      path=()
      for(input in $nativeBuildInputs) path=($path $input/bin)
      NIX9_INCLUDE_DIRS=()
      NIX9_APE_INCLUDE_DIRS=()
      NIX9_LIBRARY_DIRS=()
      for(input in $buildInputs) {
        if(test -d $input/include) NIX9_INCLUDE_DIRS=($NIX9_INCLUDE_DIRS $input/include)
        if(test -d $input/include/ape) NIX9_APE_INCLUDE_DIRS=($NIX9_APE_INCLUDE_DIRS $input/include/ape)
        if(test -d $input/lib) NIX9_LIBRARY_DIRS=($NIX9_LIBRARY_DIRS $input/lib)
        if(test -d $input/lib) {
          cp -rs --update=none $input/lib/. $NIX9_ROOT/amd64/lib/
          chmod -R u+w $NIX9_ROOT/amd64/lib
        }
      }
      ${pkgs.bash}/bin/bash ${./prepare-source.sh} --root
    '';
  stdenv = import ../../lib/stdenv.nix {
    inherit
      tools
      shell
      cc
      libc
      initialPath
      ;
    shellArgs = [
      "-e"
      "-c"
    ];
    buildPlatform = pkgs.stdenv.buildPlatform;
    hostPlatform = {
      system = "x86_64-plan9";
    };
    prepareSource = ''
      ${pkgs.bash}/bin/bash ${./prepare-source.sh}
    '';
    inherit setup;
  };
in
stdenv
// {
  mkShell = pkgs.callPackage ./shell.nix { inherit setup shell tools; };
}
