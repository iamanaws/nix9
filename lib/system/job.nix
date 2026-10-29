{ mkDerivation, buildEnv }:
{
  name,
  user,
  command,
  packages ? [ ],
  ...
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  environment = buildEnv {
    name = "nix9-job-${name}-packages";
    paths = packages;
  };
in
mkDerivation {
  name = "nix9-job-${name}";
  buildCommand = ''
    mkdir -p $out
    echo -n ${quote (command + "\n")} > $out/command
    echo '#!/bin/rc' > $out/run
    echo 'job='$out >> $out/run
    echo ${quote "jobName=${quote name}"} >> $out/run
    echo ${quote "jobUser=${quote user}"} >> $out/run
    echo ${quote "jobEnvironment=${environment}"} >> $out/run
    echo -n ${quote (builtins.readFile ./job.rc)} >> $out/run
    chmod 755 $out/run
  '';
}
