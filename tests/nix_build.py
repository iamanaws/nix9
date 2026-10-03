"""Build derivations with native Nix and compare their paths with host Nix."""

import json
import re
import shutil
import subprocess

from c_abi import EXPECTED as ABI_EXPECTED
from sha1sum import FIXTURES as SUM_FIXTURES, check_sha1sum

STORE = "local?store=/tmp/n9/store&state=/tmp/n9/state&log=/tmp/n9/log"


def build_fixtures(root, hello, abi, packages, tools):
    shutil.copytree(tools, root / "native-tools")
    (root / "native-tools.nar").write_bytes(subprocess.check_output(["nix-store", "--dump", str(tools)]))
    shutil.copytree(abi, root / "abi")
    (root / "abi.nar").write_bytes(subprocess.check_output(["nix-store", "--dump", str(abi)]))
    shutil.copytree(packages, root / "packages")
    (root / "packages.nar").write_bytes(subprocess.check_output(["nix-store", "--dump", str(packages)]))
    sums = root / "sums"
    sums.mkdir()
    shutil.copyfile(packages / "cross", sums / "cross")
    (sums / "cross").chmod(0o755)
    for name, data in SUM_FIXTURES.items():
        (sums / name).write_bytes(data)
    (root / "sums.nar").write_bytes(subprocess.check_output(["nix-store", "--dump", str(sums)]))
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
        mkDerivation = import ./packages/mk-derivation.nix { tools = ./native-tools; };
        abi = import ./abi/native.nix { inherit mkDerivation; };
        libsec = import ./packages/libsec.nix {
          inherit mkDerivation; src = ./packages/libsec;
        };
      in {
        inherit good abi libsec;
        sha1sum = import ./packages/sha1sum.nix {
          inherit mkDerivation libsec; src = ./packages/sha1sum.c;
        };
        library = abi.library;
        hello = import ./native.nix { inherit mkDerivation; };
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
    return {name: root / name for name in (path.name, nar.name, "main.c", "native.nix", "abi.nar", "packages.nar", "sums.nar", "native-tools.nar")}, expected


def check_nix_build(guest, expected):
    guest.command("/tmp/nix-store --restore /tmp/native-tools < /tmp/native-tools.nar")
    guest.command("/tmp/nix-store --restore /tmp/abi < /tmp/abi.nar")
    guest.command("/tmp/nix-store --restore /tmp/packages < /tmp/packages.nar")
    guest.command("/tmp/nix-store --restore /tmp/sums < /tmp/sums.nar")
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
    abi, library = expected["abi"], expected["library"]
    guest.command(f"{store} --query --references {abi['drv']}", library["drv"])
    inputs = guest.command(f"{store} --query --references {library['drv']}")
    for name in ("callee.c", "abi.h", "native-tools"):
        if not re.search(r"(?m)^/tmp/n9/store/[a-z0-9]{32}-" + re.escape(name) + "$", inputs):
            raise RuntimeError(f"missing library input {name}:\n{inputs}")
    sums, libsec = expected["sha1sum"], expected["libsec"]
    guest.command(f"{store} --query --references {sums['drv']}", libsec["drv"])
    guest.command("rm -rf /tmp/main.c /tmp/abi /tmp/packages /tmp/native-tools")
    guest.command("mkdir /tmp/n9-empty")
    hidden = ("/sys/include", "/amd64/include", "/amd64/lib", "/rc/lib")
    for directory in hidden:
        guest.command(f"bind /tmp/n9-empty {directory}")
    hidden_tools = ("6a", "6c", "6l", "ar", "awk", "cp", "mpc", "rc", "mkdir")
    for tool in hidden_tools:
        guest.command(f"bind /dev/null /amd64/bin/{tool}")
        guest.command(f"test ! -s /amd64/bin/{tool}")
    guest.command("test ! -e /amd64/lib/libc.a && test ! -e /sys/include/libc.h")
    guest.command(f"{store} --realise {hello['drv']}", hello["out"])
    output = guest.command(f"{hello['out']}/bin/hello-c", "Hello from Nix-built C on 9front/amd64!")
    for line in ("PASS: C file create/write/seek/read/remove", "PASS: C pipe/fork/exec/wait"):
        if line not in output.splitlines():
            raise RuntimeError(f"missing native C result: {line}")
    guest.command(f"{store} --verify-path {hello['out']}")

    guest.command(f"test ! -e {library['out']} && test ! -e {abi['out']}")
    guest.command(f"{store} --realise {abi['drv']}", abi["out"])
    output = guest.command(f"{abi['out']}/bin/abi-tests alpha 23", ABI_EXPECTED[-1])
    for line in ABI_EXPECTED:
        if line not in output.splitlines():
            raise RuntimeError(f"missing native library result: {line}")
    guest.command(f"{store} --check-validity {library['out']}")
    guest.command(f"{store} --verify-path {abi['out']} {library['out']}")
    output = guest.command(f"{store} --realise {abi['drv']}", abi["out"])
    if re.search(r"(?m)^building '", output):
        raise RuntimeError(f"native library or consumer was rebuilt:\n{output}")

    guest.command(f"test ! -e {libsec['out']} && test ! -e {sums['out']}")
    guest.command(f"{store} --realise {sums['drv']}", sums["out"])
    check_sha1sum(guest, {"native": f"{sums['out']}/bin/sha1sum", "cross": "/tmp/sums/cross"}, "/tmp/sums")
    guest.command(f"{store} --verify-path {sums['out']} {libsec['out']}")
    output = guest.command(f"{store} --realise {sums['drv']}", sums["out"])
    if re.search(r"(?m)^building '", output):
        raise RuntimeError(f"libsec or sha1sum was rebuilt:\n{output}")

    for tool in hidden_tools:
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
    output = guest.command(f"{store} --gc; echo GC-STATUS:$status")
    if not re.search(r"(?m)^GC-STATUS:.*cc9exit=1$", output) or "already open by another client" not in output:
        raise RuntimeError(f"collector opened store during a build:\n{output}")
    guest.command(f"test -e {cancel['drv']} && test -e /proc/^`{{cat /tmp/n9-builder-pid}}")
    guest.command("echo interrupt > /proc/^$job^/note")
    guest.command("wait $job; grep 'interrupted by the user' /tmp/n9-cancel-log")
    guest.command("test ! -e /proc/^`{cat /tmp/n9-builder-pid}")
    guest.command("test ! -e /proc/^`{cat /tmp/n9-sleeper-pid}")
    guest.command(f"test ! -e {cancel['out']} && test ! -e {cancel['out']}.lock")
    guest.command("test ! -e /tmp/n9-late")
    guest.command(f"{store} --verify-path {parent['out']} {good['out']}")
    return ["host derivation paths", "native builders", "C compilation with store toolchain, shell and sources", "separate C library and consumer", "libsec and sha1sum (23 native/cross cases)", "dependencies", "references", "logs",
            "reuse", "failed-output cleanup", "unsupported modes", "cancellation and child cleanup"]
