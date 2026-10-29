{
  lib,
  mkDerivation,
  buildEnv,
  authPackage,
  cpuPackage,
  configuration,
  auth,
}:
let
  inherit (configuration) enable jobs;
  names = builtins.attrNames jobs;
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] value + "'";
  makeJob = import ./job.nix { inherit mkDerivation buildEnv; };
  tasks = lib.mapAttrs (name: job: makeJob (job // { inherit name; })) jobs;
  dispatchers = lib.mapAttrs (
    name: job:
    if job.target == null then
      tasks.${name}
    else
      makeJob {
        name = "${name}.remote";
        inherit (job) user;
        packages = [ cpuPackage ];
        command = "exec ${cpuPackage}/bin/rcpu -h ${quote job.target} -u ${quote job.user} -k ${quote job.keyPattern} -t ${toString job.timeout} -c ${
          quote ("exec /$cputype/bin/rc " + toString tasks.${name} + "/run")
        }";
      }
  ) jobs;
  users = lib.unique (map (job: job.user) (builtins.attrValues jobs));
in
builtins.deepSeq
  (
    [ configuration.keyFile ]
    ++ map (job: [
      job.schedule
      job.user
      job.command
      job.target
      job.keyPattern
      job.timeout
    ]) (builtins.attrValues jobs)
  )
  (
    if !enable && (jobs != { } || configuration.keyFile != null) then
      throw "mkSystem: services.cron jobs and keyFile require services.cron.enable"
    else if enable && !auth.enable then
      throw "mkSystem: services.cron requires services.auth.enable"
    else if
      !builtins.all (
        name:
        builtins.stringLength name <= 63 && builtins.match "[a-z0-9]([a-z0-9-]*[a-z0-9])?" name != null
      ) names
    then
      throw "mkSystem: cron job names must be lowercase labels of at most 63 characters"
    else if !enable then
      null
    else
      {
        inherit tasks;
        tables = builtins.listToAttrs (
          map (
            user:
            lib.nameValuePair user (
              lib.concatMapStrings (
                name:
                let
                  job = jobs.${name};
                in
                lib.optionalString (
                  job.user == user
                ) "${job.schedule} local /$cputype/bin/rc ${dispatchers.${name}}/run\n"
              ) names
            )
          ) users
        );
        start = ''
          #!/bin/rc
          rfork ne
          . /usr/local/pkg/nix9/activate || exit 'cannot activate scheduler'
          exec ${authPackage}/bin/auth/cron -s $nix9SystemRoot
        '';
      }

  )
