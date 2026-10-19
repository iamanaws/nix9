{
  runCommand,
  python3,
  nixUtil,
}:
runCommand "nix-${nixUtil.version}-9front"
  {
    passthru.guestActivation = ''
      NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'
    '';
  }
  ''
    mkdir -p "$out/bin"
    for command in nix-store nix-instantiate nix-build; do
      ${python3}/bin/python ${nixUtil.cc9.elf2aout} ${nixUtil}/$command.elf "$out/bin/$command"
      chmod +x "$out/bin/$command"
    done
  ''
