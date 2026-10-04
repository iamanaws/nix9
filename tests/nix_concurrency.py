"""Independent native clients build together; GC requires exclusive access."""

from pathlib import Path
import re


STORE = "local?store=/tmp/n9-clients/store&state=/tmp/n9-clients/state&log=/tmp/n9-clients/log"


def concurrency_fixtures():
    fixture = Path(__file__).with_name("concurrent-builds.nix")
    return {fixture.name: fixture}


def check_concurrent_builds(guest):
    guest.command(f"clientstore='{STORE}'")
    guest.command("fn client { /tmp/nix-store --store $clientstore $* }")
    for name in ("a", "b"):
        guest.command(f"{name}=`{{$instantiate --store $clientstore /tmp/concurrent-builds.nix -A {name}}}")
        guest.command(f"{{exec /tmp/nix-store --store $clientstore --realise ${name} --add-root /tmp/n9-clients/state/gcroots/{name}}} "
                      f"> /tmp/n9-client-{name}.log >[2=1] &")
        guest.command(f"job{name}=$apid")
    for name in ("a", "b"):
        marker = f"/tmp/n9-clients-client-{name}.ready"
        guest.command(f"for(i in 1 2 3 4 5 6 7 8 9 10) {{if(! test -e {marker}) sleep 1}}; test -e {marker}")
    # Both builders are blocked at the same barrier. A third client requests a.
    guest.command("{exec /tmp/nix-store --store $clientstore --realise $a --add-root /tmp/n9-clients/state/gcroots/a} "
                  "> /tmp/n9-client-waiter.log >[2=1] &")
    guest.command("waiter=$apid; members=/tmp/n9-clients/state/db/clients")
    guest.command("for(i in 1 2 3 4 5) {if(test `{ls $members | wc -l} -lt 3) sleep 1}; "
                  "test `{ls $members | wc -l} -eq 3")
    guest.command("input=`{client -q --references $a}; client --verify-path $input")
    result = guest.command("client --gc; echo GC-STATUS:$status")
    if not re.search(r"(?m)^GC-STATUS:.*cc9exit=1$", result) or "exclusive store access required" not in result:
        raise RuntimeError(f"GC did not refuse active clients: {result}")
    guest.command("cat $input", "concurrent native builds")
    guest.command("echo release > /tmp/n9-clients-release")
    for job in ("joba", "jobb", "waiter"):
        guest.command(f"wait ${job}")
    for name in ("a", "b", "waiter"):
        root = "/tmp/n9-clients/state/gcroots/" + ("a" if name == "waiter" else name)
        guest.command(f"cat /tmp/n9-client-{name}.log", root)
    for name in ("a", "b"):
        guest.command(f"test `{{wc -l < /tmp/n9-clients-client-{name}.count}} -eq 1")
        guest.command(f"output=`{{cat /tmp/n9-clients/state/gcroots/{name}}}; client --verify-path $output")
    guest.command("client --gc")
    guest.command("output=`{cat /tmp/n9-clients/state/gcroots/a}; cat $output", "concurrent native builds")
    guest.command("test `{ls $members | wc -l} -eq 0")
    return ["overlapping builds", "shared-output reuse", "live queries", "GC exclusion", "client cleanup"]
