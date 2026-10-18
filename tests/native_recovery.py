"""Recover an interrupted build and SQLite write in a disposable guest."""

import re


def reject_recovery(guest):
    result = guest.command("nix-store --recover; echo RECOVER-STATUS:$status")
    if not re.search(r"(?m)^RECOVER-STATUS:.*cc9exit=1$", result) or "recovery requires a reboot" not in result:
        raise RuntimeError(f"recovery accepted a store used this boot: {result}")


def interrupt_build(guest):
    guest.command("roots=/usr/local/nix/state/gcroots")
    guest.command("echo keep > /tmp/keep.lock; keep=`{nix-store --add /tmp/keep.lock}")
    guest.command("nix-store --realise $keep --add-root $roots/keep")
    guest.command("echo -n > /tmp/empty.lock; empty=`{nix-store --add /tmp/empty.lock}")
    guest.command("nix-store --realise $empty --add-root $roots/empty")
    reject_recovery(guest)  # Refuse even after the last client has closed.
    guest.command("nix-instantiate /tmp/recovery.nix --add-root $roots/recovery")
    guest.command("drv=`{cat $roots/recovery}; output=`{nix-store -q --outputs $drv}")
    guest.command("{exec nix-store --realise $drv} > /tmp/recovery.log >[2=1] &")
    guest.command("for(i in 1 2 3 4 5 6 7 8 9 10) {if(! test -e /tmp/nix9-recovery-ready) sleep 1}; "
                  "test -e /tmp/nix9-recovery-ready")
    guest.command("cat $output", "partial")
    guest.command("test -e $output^.lock")
    guest.command("test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 1")
    reject_recovery(guest)
    guest.command("test -e $output^.lock && test `{ls /usr/local/nix/state/db/clients | wc -l} -eq 1")
    guest.command("db=/usr/local/nix/state/db/db.sqlite")
    guest.command("{exec /tmp/store-probe sqlite-crash $db} > /tmp/db-crash.log >[2=1] &")
    guest.command("for(i in 1 2 3 4 5 6 7 8 9 10) {if(! test -e /tmp/nix9-db-ready) sleep 1}; "
                  "cat /tmp/db-crash.log; test -e /tmp/nix9-db-ready")
    guest.command("test -e $db^.p9lock && test -s $db^-journal")
    guest.command("mkdir /usr/local/nix/store/tmp-recovery; echo -n > /usr/local/nix/store/tmp-recovery/.lock")
    # Persist the dirty database, journal and build markers, then kill QEMU.
    # This tests rollback after reboot, not torn writes or write ordering.
    guest.command("echo sync >> /srv/hjfs.cmd")
    guest.command("sleep 3")
    guest.crash()


def recover_build(guest):
    guest.command("state=/usr/local/nix/state; store=/usr/local/nix/store")
    guest.command("test `{ls $state/db/clients | wc -l} -eq 1")
    guest.command("db=$state/db/db.sqlite; test -e $db^.p9lock && test -s $db^-journal")
    guest.command("if(cmp $db /tmp/nix9-db-before) {echo unchanged}; if not {echo dirty}", "dirty")
    guest.command("nix-store --recover", "store recovery complete")
    guest.command("nix-store --recover", "store recovery complete")
    guest.command("/tmp/store-probe sqlite-recover $db", "SQLite reboot recovery PASS")
    guest.command("test `{ls $state/db/clients | wc -l} -eq 0")
    guest.command("test `{ls $state/temproots | wc -l} -eq 0")
    guest.command("test -d $store/tmp-recovery && test ! -e $store/tmp-recovery/.lock")
    guest.command("drv=`{cat $state/gcroots/recovery}; output=`{nix-store -q --outputs $drv}")
    guest.command("test ! -e $output^.lock")
    reject_recovery(guest)
    guest.command("cat $output", "partial")
    result = guest.command("nix-store --check-validity $output; echo VALID-STATUS:$status")
    if not re.search(r"(?m)^VALID-STATUS:.*cc9exit=1$", result):
        raise RuntimeError(f"unfinished output was registered: {result}")
    guest.command("echo release > /tmp/nix9-recovery-release")
    guest.command("nix-store --realise $drv --add-root $state/gcroots/recovered")
    guest.command("cat $output", "complete")
    guest.command("nix-store --verify-path $drv $output")
    guest.command("nix-store --gc")
    guest.command("cat $output", "complete")
    guest.command("keep=`{cat $state/gcroots/keep}; nix-store --verify-path $keep")
    guest.command("cat $keep", "keep")
    guest.command("empty=`{cat $state/gcroots/empty}; nix-store --verify-path $empty && test -e $empty")
    guest.command("rm $state/gcroots/recovery $state/gcroots/recovered")
    guest.command("nix-store --gc")
    guest.command("test ! -e $drv && test ! -e $output")
    guest.command("test `{ls $state/db/clients | wc -l} -eq 0")
    return "offline recovery, live-store refusal, SQLite rollback, rebuild and GC passed"
