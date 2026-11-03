{
  runCommand,
  callPackage,
  python3,
  llvmPackages,
  nixUtil,
  webfs,
  ramfs,
}:
runCommand "nix-${nixUtil.version}-9front"
  {
    passthru.guestActivation = ''
      NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'
    '';
  }
  ''
    mkdir -p "$out/bin" "$out/libexec"
    for command in nix-store nix-instantiate nix-build nix-build-remote nix-daemon-worker; do
      # Keep symbols in nix-util's ELF files, outside the installed guest package.
      ${llvmPackages.llvm}/bin/llvm-strip --strip-all -o "$command.elf" ${nixUtil}/$command.elf
      ${python3}/bin/python ${nixUtil.cc9.elf2aout} "$command.elf" "$out/bin/$command"
      chmod +x "$out/bin/$command"
    done
    cp ${./shell.rc} "$out/bin/nix-shell"
    cp ${webfs}/bin/webfs "$out/bin/webfs"
    cp ${callPackage ./transport.nix { }}/bin/nix-store-service "$out/bin/"
    cp ${ramfs}/bin/ramfs "$out/libexec/nix-ramfs"
    chmod +x "$out/bin/nix-shell"
  ''
