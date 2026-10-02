"""Build derivations with native Nix and compare their paths with host Nix."""

import json
import re
import shutil
import subprocess

STORE = "local?store=/tmp/n9/store&state=/tmp/n9/state&log=/tmp/n9/log"


def build_fixtures(root, hello, tools):
    shutil.copytree(tools, root / "native-tools")
    (root / "native-tools.nar").write_bytes(subprocess.check_output(["nix-store", "--dump", str(tools)]))
    for name in ("main.c", "native.nix"):
        shutil.copyfile(hello / name, root / name)
    path = root / "build-cases.nix"
    path.write_text(r'''
      let
        mk = name: script: extra: derivation ({
          inherit name; system = "x86_64-plan9";
          builder = "/bin/rc"; args = [ "-c" script ];
        } // extra);
        good = mk "native-input"
          "/bin/echo ran >> /tmp/n9-count; /bin/echo native > $out" {};
      in {
        inherit good;
        hello = import ./native.nix { tools = ./native-tools; };
        parent = mk "native-parent"
          "/bin/echo builder-log; /bin/cat $input > $out; /bin/echo $input >> $out"
          { input = good; };
        failed = mk "native-failure" "/bin/echo partial > $out; exit failed" {};
        missing = mk "native-empty" "/bin/echo no-output" {};
        references = mk "native-refs" "/bin/echo $input > $out"
          { input = good; allowedReferences = []; };
        multiple = mk "native-multiple" "/bin/echo unexpected > $out"
          { outputs = [ "out" "dev" ]; };
        sandbox = mk "native-sandbox" "/bin/echo unexpected > $out" {};
        cancel = mk "native-cancel" ''
          /bin/echo partial > $out
          /bin/echo $pid > /tmp/n9-builder-pid
          @{/bin/rc -c '/bin/echo $pid > /tmp/n9-sleeper-pid; exec /bin/sleep 30'}
          /bin/echo leaked > /tmp/n9-late
        '' {};
      }
    ''')
    expected = json.loads(subprocess.check_output([
        "nix-instantiate", "--store", "dummy://?store=/tmp/n9/store", "--eval", "--strict", "--json",
        "--expr", 'builtins.mapAttrs (_: d: { drv = d.drvPath; out = d.outPath; }) (import ' + str(path) + ')',
    ], text=True))
    content = root / "build-parent-content"
    content.write_text("native\n" + expected["good"]["out"] + "\n")
    nar = root / "build-parent.nar"
    nar.write_bytes(subprocess.check_output(["nix-store", "--dump", str(content)]))
    return {name: root / name for name in (path.name, nar.name, "main.c", "native.nix", "native-tools.nar")}, expected


def check_nix_build(guest, expected):
    guest.command("/tmp/nix-store --restore /tmp/native-tools < /tmp/native-tools.nar")
    guest.command(f"buildstore='{STORE}'")
    evaluate = "/tmp/nix-eval --store $buildstore --instantiate"
    store = "/tmp/nix-store --store $buildstore"
    for name, paths in expected.items():
        guest.command(f"{evaluate} --expr '(import /tmp/build-cases.nix).{name}'", paths["drv"])
        guest.command(f"{store} --check-validity {paths['drv']}")

    hello = expected["hello"]
    inputs = guest.command(f"{store} --query --references {hello['drv']}")
    for name in ("main.c", "native-tools"):
        if not re.search(r"(?m)^/tmp/n9/store/[a-z0-9]{32}-" + re.escape(name) + "$", inputs):
            raise RuntimeError(f"missing derivation input {name}:\n{inputs}")
    guest.command("rm -rf /tmp/main.c /tmp/native-tools")
    guest.command("mkdir /tmp/n9-empty")
    hidden = ("/sys/include", "/amd64/include", "/amd64/lib")
    for directory in hidden:
        guest.command(f"bind /tmp/n9-empty {directory}")
    for tool in ("6c", "6l"):
        guest.command(f"bind /dev/null /amd64/bin/{tool}")
        guest.command(f"test ! -s /amd64/bin/{tool}")
    guest.command("test ! -e /amd64/lib/libc.a && test ! -e /sys/include/libc.h")
    guest.command(f"{store} --realise {hello['drv']}", hello["out"])
    output = guest.command(f"{hello['out']}/bin/hello-c", "Hello from Nix-built C on 9front/amd64!")
    for line in ("PASS: C file create/write/seek/read/remove", "PASS: C pipe/fork/exec/wait"):
        if line not in output.splitlines():
            raise RuntimeError(f"missing native C result: {line}")
    guest.command(f"{store} --verify-path {hello['out']}")

    for tool in ("6c", "6l"):
        guest.command(f"unmount /dev/null /amd64/bin/{tool}")
    for directory in hidden:
        guest.command(f"unmount /tmp/n9-empty {directory}")

    parent, good = expected["parent"], expected["good"]
    guest.command(f"{store} --realise {parent['drv']}", parent["out"])
    guest.command(f"cat {good['out']}", "native")
    guest.command(f"{store} --query --references {parent['out']}", good["out"])
    guest.command(f"{store} --verify-path {parent['out']} {good['out']}")
    guest.command(f"/tmp/nix-store --dump {parent['out']} > /tmp/build-result.nar")
    guest.command("cmp /tmp/build-result.nar /tmp/build-parent.nar")
    guest.command(f"{store} --read-log {parent['drv']}", "builder-log")
    guest.command(f"{store} --realise {parent['drv']}", parent["out"])
    guest.command("test `{cat /tmp/n9-count | wc -l} -eq 1")

    for name, option, message in (
        ("failed", "", "failed"),
        ("missing", "", "did not produce"),
        ("references", "", "not allowed"),
        ("multiple", "", "one input-addressed output"),
        ("sandbox", "--option sandbox true", "sandboxed builds are not supported"),
    ):
        paths = expected[name]
        output = guest.command(f"{store} {option} --realise {paths['drv']}; echo BUILD-STATUS:$status")
        if not re.search(r"(?m)^BUILD-STATUS:.*cc9exit=[1-9][0-9]*$", output) or message not in output:
            raise RuntimeError(f"expected build failure ({name}):\n{output}")
        guest.command(f"test ! -e {paths['out']} && test ! -e {paths['out']}.lock")
    guest.command(f"{store} --verify-path {parent['out']} {good['out']}")
    cancel = expected["cancel"]
    guest.command(f"{{exec {store} --realise {cancel['drv']}}} "
                  "> /tmp/n9-cancel-log >[2=1] &")
    guest.command("job=$apid; for(i in 1 2 3 4 5) {if(! test -e /tmp/n9-sleeper-pid) sleep 1}; "
                  "test -e /tmp/n9-sleeper-pid")
    guest.command("test `{cat /tmp/n9-builder-pid} -ne `{cat /tmp/n9-sleeper-pid}")
    guest.command("echo interrupt > /proc/^$job^/note")
    guest.command("wait $job; grep 'interrupted by the user' /tmp/n9-cancel-log")
    guest.command("test ! -e /proc/^`{cat /tmp/n9-builder-pid}")
    guest.command("test ! -e /proc/^`{cat /tmp/n9-sleeper-pid}")
    guest.command(f"test ! -e {cancel['out']} && test ! -e {cancel['out']}.lock")
    guest.command("test ! -e /tmp/n9-late")
    guest.command(f"{store} --verify-path {parent['out']} {good['out']}")
    return ["host derivation paths", "native builders", "C compilation with store toolchain and sources", "dependencies", "references", "logs",
            "reuse", "failed-output cleanup", "unsupported modes", "cancellation and child cleanup"]
