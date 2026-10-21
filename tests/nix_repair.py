"""Repair native outputs from their derivations without a binary cache."""

import re


def check_repairs(guest):
    guest.command("previousRepairConfig=$NIX_CONFIG; NIX_CONFIG='substituters ='")
    guest.command("fn repair { cliBuild /tmp/nix-build.nix -A repair --repair --no-out-link }")
    guest.command("cliBuild /tmp/nix-build.nix -A repair -o $roots/repair")
    guest.command("cliBuild /tmp/nix-build.nix -A repair.dev -o $roots/repair")
    guest.command("repairOut=`{cat $roots/repair}; repairDev=`{cat $roots/repair-dev}")
    guest.command("repairDep=`{cat $repairOut/dependency}")
    for name in ("Out", "Dev"):
        guest.command(f"cliStore --dump $repair{name} > /tmp/repair-{name}.nar")
    guest.command("chmod 666 $repairOut/message; echo damaged > $repairOut/message")
    guest.command("cliStore --dump $repairOut > /tmp/repair-damaged.nar")
    guest.command("echo /tmp/n9-cli-build/store/* > /tmp/repair-store-before")
    guest.command("echo flag > /tmp/nix9-repair-change")
    for flag, reason, status in (("fail", "repair-builder-failed", 100), ("missing", "did not produce 'out'", 1)):
        guest.command(f"echo flag > /tmp/nix9-repair-{flag}")
        command = "cliStore --repair-path $repairOut" if flag == "fail" else "repair"
        result = guest.command(command + "; echo REPAIR-STATUS:$status")
        if reason not in result or not re.search(rf"(?m)^REPAIR-STATUS:.*cc9exit={status}$", result):
            raise RuntimeError(f"incorrect repair failure ({flag}): {result}")
        guest.command(f"rm /tmp/nix9-repair-{flag}")
        preserved(guest)

    guest.command("echo flag > /tmp/nix9-repair-cancel")
    guest.command("{exec /tmp/nix-build --store $clistore /tmp/nix-build.nix -A repair --repair --no-out-link} > /tmp/repair.log >[2=1] &")
    guest.command("job=$apid; for(i in 1 2 3 4 5) {if(! test -e /tmp/nix9-repair-child) sleep 1}; test -e /tmp/nix9-repair-child")
    guest.command("echo interrupt > /proc/^$job^/note")
    guest.command("wait $job; grep 'interrupted by the user' /tmp/repair.log")
    guest.command("test ! -e /proc/^`{cat /tmp/nix9-repair-pid} && test ! -e /proc/^`{cat /tmp/nix9-repair-child}")
    guest.command("rm /tmp/nix9-repair-cancel")
    preserved(guest)
    guest.command("repair")
    restored(guest)
    guest.command("repair; test `{wc -l < /tmp/nix9-repair-count} -eq 5")
    guest.command("rm /tmp/nix9-repair-change")

    # Missing registered outputs and damaged dependencies use upstream repair fallback.
    guest.command("chmod 777 $repairOut; rm -r $repairOut")
    guest.command("cliStore --repair-path $repairOut")
    restored(guest)
    guest.command("chmod 666 $repairDep; echo damaged > $repairDep")
    guest.command("repair; cat $repairDep", "dependency")
    guest.command("cliStore --verify-path $repairOut $repairDev $repairDep")

    # Rejecting cyclic references at registration must roll back every replacement.
    guest.command("chmod 666 $repairOut/message $repairDev; echo damaged > $repairOut/message; echo damaged > $repairDev")
    guest.command("cliStore --dump $repairDev > /tmp/repair-damaged-dev.nar")
    guest.command("echo flag > /tmp/nix9-repair-cycle")
    result = guest.command("repair; echo REPAIR-STATUS:$status")
    if "cycle" not in result or not re.search(r"(?m)^REPAIR-STATUS:.*cc9exit=1$", result):
        raise RuntimeError(f"repair did not reject a reference cycle: {result}")
    guest.command("cliStore --dump $repairOut > /tmp/repair-current.nar; cmp /tmp/repair-current.nar /tmp/repair-damaged.nar")
    guest.command("cliStore --dump $repairDev > /tmp/repair-current.nar; cmp /tmp/repair-current.nar /tmp/repair-damaged-dev.nar")
    guest.command("rm /tmp/nix9-repair-cycle; repair")
    restored(guest)

    guest.command("cliBuild /tmp/nix-build.nix -A fixedRepair -o $roots/fixed-repair")
    guest.command("fixedRepair=`{cat $roots/fixed-repair}; chmod 666 $fixedRepair; echo damaged > $fixedRepair")
    guest.command("echo flag > /tmp/nix9-fixed-wrong")
    result = guest.command("cliBuild /tmp/nix-build.nix -A fixedRepair --repair --no-out-link; echo REPAIR-STATUS:$status")
    if "hash mismatch" not in result or not re.search(r"(?m)^REPAIR-STATUS:.*cc9exit=102$", result):
        raise RuntimeError(f"repair accepted a wrong fixed-output hash: {result}")
    guest.command("cat $fixedRepair", "damaged")
    guest.command("rm /tmp/nix9-fixed-wrong")
    guest.command("cliBuild /tmp/nix-build.nix -A fixedRepair --repair --no-out-link")
    guest.command("cat $fixedRepair", "fixed")
    guest.command("cliStore --verify-path $fixedRepair")
    guest.command("rm $roots/repair $roots/repair-dev $roots/fixed-repair; cliStore --gc")
    guest.command("test ! -e $repairOut && test ! -e $repairDev && test ! -e $fixedRepair")
    guest.command("NIX_CONFIG=$previousRepairConfig")


def preserved(guest):
    guest.command("cliStore --dump $repairOut > /tmp/repair-current.nar; cmp /tmp/repair-current.nar /tmp/repair-damaged.nar")
    guest.command("cliStore --dump $repairDev > /tmp/repair-current.nar; cmp /tmp/repair-current.nar /tmp/repair-Dev.nar")
    guest.command("cliStore --verify-path $repairDev")
    guest.command("echo /tmp/n9-cli-build/store/* > /tmp/repair-store-after; cmp /tmp/repair-store-before /tmp/repair-store-after")


def restored(guest):
    for name in ("Out", "Dev"):
        guest.command(f"cliStore --dump $repair{name} > /tmp/repair-current.nar; cmp /tmp/repair-current.nar /tmp/repair-{name}.nar")
    guest.command("cliStore --verify-path $repairOut $repairDev")
