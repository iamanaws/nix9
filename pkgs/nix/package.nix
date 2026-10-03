{
  runCommand,
  python3,
  nixUtil,
  nativeTools,
  secSource,
  sha1sum,
}:
runCommand "nix-${nixUtil.version}-9front"
  {
    passthru.guestActivation = ''
      NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'
    '';
  }
  ''
    mkdir -p "$out/bin" "$out/share/nix9/pkgs"
    for command in nix-store nix-eval; do
      ${python3}/bin/python ${nixUtil.cc9.elf2aout} ${nixUtil}/$command.elf "$out/bin/$command"
      chmod +x "$out/bin/$command"
    done
    cp -r ${nativeTools} "$out/share/nix9/tools"
    cp -r ${secSource} "$out/share/nix9/libsec-source"
    cp ${sha1sum.source} "$out/share/nix9/sha1sum.c"
    cp ${../../lib/mk-derivation.nix} "$out/share/nix9/mk-derivation.nix"
    cp ${../libsec/native.nix} "$out/share/nix9/pkgs/libsec.nix"
    cp ${../sha1sum/native.nix} "$out/share/nix9/pkgs/sha1sum.nix"
    cp ${./packages.nix} "$out/share/nix9/default.nix"
  ''
