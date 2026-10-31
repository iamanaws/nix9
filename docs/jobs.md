# Scheduled jobs

`services.cron` runs native `auth/cron` on an authentication server booted in
CPU mode. Accounts, authentication keys and native Nix permissions must already
be provisioned. Use an account that can operate that machine's Nix store and
state, normally the account that installed Nix. Add a local job to its module:

```nix
{
  services.cron = {
    enable = true;
    jobs.report = {
      schedule = "0 6 * * 1-5";
      user = "glenda";
      command = "echo daily-report; ls /usr/glenda/projects";
    };
  };
}
```

`services.auth.enable` must also be true. `packages` adds packages to a job's
command environment; store paths interpolated in `command` are retained too.
Commands use rc and run as `user` in a fresh native user namespace. The file
server's permissions still apply.

Schedules have five fields: minute (0–59), hour (0–23), day (1–31), month
(1–12), weekday (0–6, Sunday first). Each accepts `*`, a number, an inclusive
range or a comma-separated list. For example, `0,30 9-17 * * 1-5` runs twice
an hour on weekdays. Step syntax such as `*/5` is unsupported. All five fields
must match; day and weekday use AND. Times use the scheduler's native timezone.

## Across an installation

Declare relationships by inventory key:

```nix
{
  jobs.report = {
    scheduler = "files";
    target = "cpu";
    schedule = "0 6 * * *";
    user = "glenda";
    command = "cat /n/projects/report";
  };
  machines.files.configuration.services.cron.keyFile = "/adm/scheduler.keys";
}
```

The [installation](installation.md) enables cron on the scheduler and includes
the command closure and log directory in the target system. Evaluation requires
an authentication scheduler and, for a remote target, CPU access allowing the
job's user. The manifest records the job and its runtime dependency. A target
matching the scheduler runs locally.

Remote jobs use authenticated `rcpu`. `keyPattern` defaults to the installation's
`defaults.authdom`; `timeout` defaults to 10 seconds for connection setup.
`services.cron.keyFile` loads private runtime factotum key commands at CPU boot,
independently of export services. Its default, `null`, uses provisioned keys.
Supply the job user's client key and configure [CPU delegation](access.md) for
any [session shares](sharing.md) used on the target. Keys belong in private runtime files, never in job commands or the store.
The job uses the target's session mounts and its own machine-local Nix store.

Deploy the target system before selecting the scheduler's changed schedule.
Running jobs use the command closure named by that schedule. Missing target
closures, failed authentication or unavailable required shares fail that run.
With standalone `mkSystem`, `target` is a CPU hostname. Transfer the command
closure listed in `SYSTEM/services/cron/commands/NAME` to that machine and
prepare its log directory there.

## Updates and results

Enabling cron requires a CPU-server reboot. A running scheduler reads the
selected system every minute: selection, rollback and removal update future
runs without restarting it. Disabling cron stops new runs within a minute; the
daemon exits at reboot. Started jobs continue. Native `/cron/lock` excludes a
second scheduler; remove manual cron startup before enabling management. Managed
mode reads generated tables instead of writable `/cron/USER/cron` tables.

Each job records output, start/end timestamps and exit status in an append-only
log:
`/sys/log/nix9-jobs/USER/NAME.log`, with mode `0600` in a `0700` user directory.
Remote dispatch results use `NAME.remote.log` on the scheduler; command output
uses `NAME.log` on the target. Scheduler diagnostics use `/sys/log/cron`.
Directories and the scheduler log use the existing preparation modules; cron
enables log preparation by default. Its scheduler log uses `0660` for the stock
image's `sys` group; override `logging.files.cron.mode` for other ownership.
Logs survive selection and rollback; rotation is manual.

Every execution roots its command closure and active system under
`/usr/local/nix/state/gcroots/jobs/USER/` before running and releases both roots
on normal completion or handled exit. This protects commands and namespace
resources when old system generations are deleted and collected. A hard kill or crash can leave a
root; remove it only after checking that its job has stopped.

Cron provides periodic attempts, without a durable queue, automatic retries or
an overlap guard. A failed run waits for the next matching schedule; long jobs
can overlap. Clock jumps can trigger native cron's catch-up behavior. The
connection timeout does not limit command duration. Keep commands in the
foreground so their closure remains rooted for their full lifetime.
