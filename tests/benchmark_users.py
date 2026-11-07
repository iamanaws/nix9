"""Develop the pinned clone utility on the reference four-machine installation."""

import argparse
from contextlib import nullcontext
import json
import hashlib
from pathlib import Path
import re
import secrets
import tempfile

from lab_support import attach_console, detach_console, start_lab, stop_lab, write_file
from user_performance import Timings, cpu_session, development_session, quote


def output_path(output):
    paths = re.findall(r"(?m)^/usr/local/nix/store/\S+$", output)
    if len(paths) != 1:
        raise RuntimeError("expected one store output: " + output)
    return paths[0]


def reused(output, expected):
    if output_path(output) != expected or "building '" in output or "copying path" in output:
        raise RuntimeError("unchanged project was not reused: " + output)


def copy_checks(guest, project, program, directory):
    guest.command("mkdir -p " + directory)
    guest.command("awk " + quote('BEGIN { for(i=0;i<4096;i++) print i, "clone benchmark payload" }')
                  + " > " + directory + "/payload")
    guest.command("rc " + project + "/copy.rc " + program + " " + directory + "/tree "
                  + directory + "/payload", "upstream-clone-PASS")
    output = guest.command("rc -c " + quote(program + " " + directory + "/missing "
                                           + directory + "/unexpected") + "; echo CLONE-ERROR:$status")
    if not re.search(r"(?m)^CLONE-ERROR:.+", output):
        raise RuntimeError("clone accepted a missing source")


def check_usage(guest, program, text):
    output = guest.command("rc -c " + quote(program) + "; echo CLONE-ERROR:$status")
    if text not in output or not re.search(r"(?m)^CLONE-ERROR:.+", output):
        raise RuntimeError("unexpected clone source version: " + output)


def benchmark(auth, source, timings):
    run = secrets.token_hex(4)
    project = "/n/projects/clone-" + run
    print("Project: " + project, flush=True)
    profile = "/usr/local/nix/state/gcroots/per-user/alice/clone-" + run
    build_command = "cd " + project + " && nix-build default.nix --out-link " + profile + "-result"

    def remote(machine, command, expected=None, user="alice"):
        return auth.command("rcpu -u " + user + " -h " + machine + " -c " + quote(command), expected)

    def prepare():
        with cpu_session(auth, "build") as cpu:
            cpu.command("mkdir " + project + " && mkdir " + project + "/source")
            for path in sorted(source.iterdir()):
                if not path.is_file():
                    raise RuntimeError("unexpected clone source entry: " + str(path))
                write_file(cpu, project + "/source/" + path.name, path.read_bytes())
                cpu.command("nix-instantiate --eval --expr " + quote(
                    'builtins.hashFile "sha256" ' + project + "/source/" + path.name),
                    '"' + hashlib.sha256(path.read_bytes()).hexdigest() + '"')
            for name in ("default.nix", "environment.nix"):
                write_file(cpu, project + "/" + name, Path(__file__).with_name("clone-workspace").joinpath(name).read_bytes())
            write_file(cpu, project + "/copy.rc", Path(__file__).with_name("clone.rc").read_bytes())
            cpu.command("chmod 770 " + project + " " + project + "/source; chmod 660 "
                        + project + "/default.nix " + project + "/environment.nix " + project + "/copy.rc " + project + "/source/*")

    timings.measure("setup/project-transfer", prepare)
    remote("batch", "cat " + project + "/source/clone.c > /dev/null", user="bob")
    first = timings.measure("build/first-build", lambda: remote("build", build_command))
    if " on 'cpu://" not in first:
        raise RuntimeError("first project build did not compile remotely")
    original = output_path(first)
    remote("build", "cat " + original + "/nix-support/builder", "batch")
    remote("build", "cat " + original + "/nix-support/identity", "none")
    # The remote result is already in batch's store. Switching CPUs should reuse it.
    reused(timings.measure("batch/first-reuse", lambda: remote("batch", build_command)), original)
    environment = output_path(timings.measure("build/environment", lambda: remote("build",
        "cd " + project + " && nix-build environment.nix --out-link " + profile + "-environment")))

    for machine in ("build", "batch"):
        if machine == "batch":
            remote(machine, "test ! -e " + profile)
        remote(machine, "nix-profile " + profile + " set " + environment)
        remote(machine, "test ! -r /adm/builder.keys && test ! -w /usr/local/nix/store")
        directory = "/usr/alice/clone-" + run + "/" + machine
        remote(machine, "mkdir -p " + directory + "/work; cp " + project + "/source/* " + directory + "/work")
        for context in ("login", "session"):
            with (cpu_session(auth, machine) if context == "session" else nullcontext(None)) as cpu:
                execute = cpu.command if cpu else lambda command, expected=None: remote(machine, command, expected)
                prefix = machine + "/" + context + "/"
                timings.measure(prefix + "warmup-shell", lambda: execute(
                    "cd " + project + " && nix-shell default.nix --run 'echo ready'", "ready"))
                derivation = output_path(execute("nix-instantiate " + project + "/default.nix"))
                commands = (
                    ("ready", "echo ready", "ready"),
                    ("version", "nix-instantiate --version", None),
                    ("eval-constant", "nix-instantiate --eval --expr 42", "42"),
                    ("eval-packages", "nix-instantiate --eval --expr '(import <nix9>).libthread.name'", None),
                    ("read-source", "cat " + project + "/source/clone.c > /dev/null", None),
                    ("instantiate-project", "nix-instantiate " + project + "/default.nix", None),
                    ("source-import", "nix-store --add " + project + "/source", None),
                    ("realise-project", "nix-store --realise " + derivation, None),
                    ("cached-build", build_command, None),
                    ("shell-startup", "cd " + project + " && nix-shell default.nix --run 'echo ready'", "ready"),
                )
                for _ in range(3):
                    for name, command, expected in commands:
                        output = timings.measure(prefix + name, lambda: execute(command, expected))
                        if name in ("cached-build", "realise-project"):
                            reused(output, original)
                if cpu:
                    with development_session(cpu, project, directory + "/work") as shell:
                        for _ in range(3):
                            timings.measure(machine + "/shell/clean-compile", lambda: shell.command("rm -f clone.6 6.out && mk"))
                            timings.measure(machine + "/shell/unchanged-mk", lambda: shell.command("mk"))
                        copy_checks(shell, project, directory + "/work/6.out", directory + "/shell-copy")
                    timings.measure(machine + "/copy-checks", lambda: copy_checks(
                        cpu, project, original + "/bin/clone", directory + "/package-copy"))
                    check_usage(cpu, original + "/bin/clone", "usage:")

    edited_outputs = {}
    with cpu_session(auth, "build") as cpu:
        cpu.command("cp " + project + "/source/clone.c " + project + "/clone-original.c")
        cpu.command("sed 's/usage: /workspace usage: /' " + project + "/clone-original.c > " + project + "/source/clone.c")
    try:
        for machine in ("build", "batch"):
            label = "/edit-build" if machine == "build" else "/edit-reuse"
            output = timings.measure(machine + label, lambda: remote(machine, build_command))
            edited = output_path(output)
            if edited == original:
                raise RuntimeError("source edit did not change the output")
            if machine == "build" and " on 'cpu://" not in output:
                raise RuntimeError("edited source did not compile remotely")
            if machine == "batch":
                reused(output, edited_outputs["build"])
            edited_outputs[machine] = edited
            check_usage_remote = "rc -c " + quote(edited + "/bin/clone") + "; echo CLONE-ERROR:$status"
            version = remote(machine, check_usage_remote)
            if "workspace usage:" not in version or not re.search(r"(?m)^CLONE-ERROR:.+", version):
                raise RuntimeError("rebuilt clone did not contain the source edit")
            # Profiles stay independent of the latest build result.
            remote(machine, "cat " + profile, environment)
            directory = "/usr/alice/clone-" + run + "/" + machine
            with cpu_session(auth, machine) as cpu:
                with development_session(cpu, project, directory + "/work") as shell:
                    shell.command("cp " + project + "/source/clone.c clone.c")
                    timings.measure(machine + "/shell/edit-compile", lambda: shell.command("mk"))
                    check_usage(shell, "./6.out", "workspace usage:")
    finally:
        remote("build", "cp " + project + "/clone-original.c " + project + "/source/clone.c")
    for machine in ("build", "batch"):
        reused(timings.measure(machine + "/restored-build", lambda: remote(machine, build_command)), original)
    return {"project": project, "original": original, "edited": edited_outputs,
            "checks": ["remote-build", "anonymous-builder", "second-cpu-reuse", "separate-profiles",
                       "cached-builds", "parallel-copy", "empty-files", "overwrite", "missing-source",
                       "native-shell-compile", "source-edit", "restored-source-reuse"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("launcher")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, nargs="?", default=Path("nix9-users-performance"))
    parser.add_argument("--lab", type=Path, help="use an existing lab; do not stop one already running")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir()
    timings = Timings(output)
    with (nullcontext(None) if args.lab else tempfile.TemporaryDirectory(dir=output)) as temporary:
        work = args.lab.resolve() if args.lab else Path(temporary) / "lab"
        marker = work / "run.json"
        running = marker.exists() and json.loads(marker.read_text()).get("phase") == "ready"
        process, log, auth = None, None, None
        try:
            if not running:
                phase = "startup" if (work / "lab.json").exists() else "provision"
                process, log = timings.measure("setup/" + phase, lambda: start_lab(args.launcher, work, output / "launcher.log"))
            auth = attach_console(args.launcher, work)
            result = benchmark(auth, args.source, timings)
            result.update(status="passed", machines=4, reusedLab=args.lab is not None,
                          alreadyRunning=running, source=str(args.source), samples=3,
                          sourceHashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.source.iterdir())},
                          virtualCPUs=2, memoryMiB=2048, network="private virtual Ethernet",
                          clock="host monotonic wall time")
        finally:
            if auth is not None and auth.child.isalive():
                detach_console(auth)
            if process is not None and process.poll() is None:
                stop_lab(process, log, work)
            if (work / "control.log").exists() and not running:
                text = (work / "control.log").read_text(errors="replace")
                text = re.sub(r'http://10\.0\.2\.2:[0-9]+/[^\s\x00-\x1f]+', 'http://10.0.2.2/[redacted]', text)
                text = re.sub(r'("GET )/[^" ]+', r'\1/[redacted]', text)
                (output / "control.log").write_text(text)
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
