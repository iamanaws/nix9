{
  pkgs ? import <nix9>,
}:
let
  command = ''
    echo local-one
    ${pkgs.fortune}/bin/fortune
  '';
  base = {
    hostName = "jobs";
    services.auth.enable = true;
    services.cron.enable = true;
    services.cron.jobs.local = {
      schedule = "* * * * *";
      user = "glenda";
      inherit command;
    };
  };
  make =
    extra:
    pkgs.mkSystem {
      imports = [
        base
        extra
      ];
    };
  makeInstallation =
    extra:
    pkgs.mkInstallation {
      imports = [
        (<nix9> + "/examples/installation/configuration.nix")
        {
          jobs.report = {
            scheduler = "files";
            target = "cpu";
            schedule = "* * * * *";
            user = "glenda";
            timeout = 3;
            command = "echo scheduled-on-`{cat /dev/sysname}; cat /n/projects/hello.c";
          };
          machines.files.configuration.logging.enable = true;
          machines.cpu.configuration.logging.enable = true;
          machines.cpu.mounts.projects.timeout = 3;
          machines.files.configuration.services.ndb.dns.enable = false;
          machines.cpu.configuration.services.ndb.dns.enable = false;
        }
        extra
      ];
    };
  invalidSchedule = schedule: make { services.cron.jobs.local.schedule = pkgs.lib.mkForce schedule; };
  lib = pkgs.lib;
in
{
  one = make { };
  two = make { services.cron.jobs.local.command = lib.mkForce "echo local-two"; };
  disabled = make {
    services.cron = {
      enable = lib.mkForce false;
      jobs = lib.mkForce { };
    };
  };
  removed = make { services.cron.jobs = lib.mkForce { }; };
  failed = make {
    services.cron.jobs.local.command = lib.mkForce "echo intentional-failure; exit deliberate";
  };
  long = make {
    services.cron.jobs.local.command =
      lib.mkForce "echo retained-start; while(! test -f /tmp/job-finish) sleep 1; echo retained-end";
  };
  installation = makeInstallation { };
  files = (makeInstallation { }).systems.files;
  cpu = (makeInstallation { }).systems.cpu;
  reportChanged =
    (makeInstallation { jobs.report.command = lib.mkForce "echo updated-report"; }).systems.files;
  reportDisabled = (makeInstallation { jobs = lib.mkForce { }; }).systems.files;
  validKeyFile = make { services.cron.keyFile = "/adm/jobs.keys"; };
  relativeKeyFile = make { services.cron.keyFile = "jobs.keys"; };
  storedKeyFile = make { services.cron.keyFile = "${pkgs.auth}/keys"; };
  disabledKeyFile = pkgs.mkSystem {
    hostName = "jobs";
    services.cron.keyFile = "/adm/jobs.keys";
  };
  invalidMinute = invalidSchedule "60 * * * *";
  invalidHour = invalidSchedule "* 24 * * *";
  invalidDay = invalidSchedule "* * 0 * *";
  invalidMonth = invalidSchedule "* * * 13 *";
  invalidWeekday = invalidSchedule "* * * * 7";
  invalidRange = invalidSchedule "8-2 * * * *";
  invalidList = invalidSchedule "1, * * * *";
  invalidStep = invalidSchedule "*/5 * * * *";
  invalidFields = invalidSchedule "* * * *";
  injectedSchedule = invalidSchedule "* * * * *\necho bad";
  validRange = invalidSchedule "0,15,30-45 0-23 1-31 1-12 0-6";
  invalidName = make { services.cron.jobs."bad/name" = base.services.cron.jobs.local; };
  invalidUser = make { services.cron.jobs.local.user = lib.mkForce "*"; };
  invalidTimeout = make { services.cron.jobs.local.timeout = 0; };
  secretPattern = make { services.cron.jobs.local.keyPattern = "!password=secret"; };
  noAuth = make { services.auth.enable = lib.mkForce false; };
  disabledJobs = make { services.cron.enable = lib.mkForce false; };
  unknownTarget = makeInstallation { jobs.report.target = lib.mkForce "missing"; };
  unknownScheduler = makeInstallation { jobs.report.scheduler = lib.mkForce "missing"; };
  wrongScheduler = makeInstallation { jobs.report.scheduler = lib.mkForce "terminal"; };
  wrongTarget = makeInstallation { jobs.report.target = lib.mkForce "terminal"; };
  forbiddenUser = makeInstallation { jobs.report.user = lib.mkForce "nobody"; };
}
