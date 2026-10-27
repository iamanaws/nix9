{
  runCommand,
  python3,
  llvmPackages,
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
      # Keep symbols in nix-util's ELF files, outside the installed guest package.
      ${llvmPackages.llvm}/bin/llvm-strip --strip-all -o "$command.elf" ${nixUtil}/$command.elf
      ${python3}/bin/python ${nixUtil.cc9.elf2aout} "$command.elf" "$out/bin/$command"
      chmod +x "$out/bin/$command"
    done
    cp ${./shell.rc} "$out/bin/nix-shell"
    chmod +x "$out/bin/nix-shell"
  ''
