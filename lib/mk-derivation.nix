{ tools }:
attrs@{ name, buildCommand, ... }:
derivation (
  {
    inherit name tools;
    system = "x86_64-plan9";
    builder = "${tools}/bin/rc";
    args = [
      "-m"
      "${tools}/rcmain"
      "-e"
      "-c"
      ''
        rfork n
        $tools/bin/mkdir .nix-empty .nix-rc
        $tools/bin/cp $tools/rcmain .nix-rc/rcmain
        $tools/bin/bind $tools/bin /bin
        for(directory in /amd64/bin /rc/bin) /bin/bind .nix-empty $directory
        /bin/bind .nix-rc /rc/lib
        /bin/bind $tools/sys/include /sys/include
        /bin/bind $tools/amd64/include /amd64/include
        /bin/bind $tools/amd64/lib /amd64/lib
        path=(/bin)
        ${buildCommand}
      ''
    ];
  }
  // builtins.removeAttrs attrs [ "buildCommand" ]
)
