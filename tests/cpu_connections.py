"""Connection deadlines cover silent and partial setup, but not compilation."""

from contextlib import contextmanager
import re
import socket
import threading
import time


def quote(value):
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def silent_peer():
    """Accept TCP but never answer authentication; close when the helper exits."""
    stopped = threading.Event()
    closed = threading.Event()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(.2)

        def serve():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(.2)
                    while not stopped.is_set():
                        try:
                            if not connection.recv(4096):
                                closed.set()
                                break
                        except socket.timeout:
                            pass
                        except ConnectionResetError:
                            closed.set()
                            break

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield listener.getsockname()[1], closed
        finally:
            stopped.set()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("silent authentication peer did not stop")


def check_connections(terminal, build, package, build_project, failed, until):
    # Use variables to keep serial-console commands within its input buffer.
    terminal.command("setupPackage=" + quote(package))
    build.command("6c -o /tmp/cpu-setup.6 /tmp/cpu-setup.c && 6l -o /tmp/cpu-setup /tmp/cpu-setup.6")
    for name in ("silent", "partial", "retry", "delayed"):
        build.command("cp /tmp/cpu-setup /tmp/cpu-setup-" + name)
    base = "cpu://build?key-pattern=dom%3Dnix9.builders"

    def uri(name, seconds=5):
        return base + "&remote-program=/tmp/cpu-setup-" + name + "&connect-timeout=" + str(seconds)

    def query(store):
        terminal.command("setupStore=" + quote(store))
        return "nix-store --store $setupStore -q --hash $setupPackage"

    def timed_failure(command):
        started = time.monotonic()
        output = failed(terminal, command, "connection setup timed out after 5 seconds")
        elapsed = time.monotonic() - started
        if not 4 <= elapsed < 10 or "cpu://" not in output:
            raise RuntimeError(f"connection setup did not respect its deadline ({elapsed:.1f}s): {output}")
        return elapsed

    elapsed = {}
    with silent_peer() as (port, closed):
        elapsed["authentication"] = timed_failure(query(
            f"cpu://10.0.2.2:{port}?connect-timeout=5"))
        if not closed.wait(timeout=5):
            raise RuntimeError("timed-out authentication helper retained its TCP connection")
    for name in ("silent", "partial"):
        elapsed[name] = timed_failure(query(uri(name)))
        pid = re.findall(r"(?m)^\d+$", build.command("cat /tmp/cpu-setup-" + name + ".pid"))[0]
        until(build, "test ! -e /proc/" + pid)
    # Repeat failures so a retired pipe or helper cannot poison the next FD reuse.
    for _ in range(3):
        timed_failure(query(uri("silent")))
    print("PASS: authentication and partial serve handshakes time out without retaining helpers", flush=True)

    failed(terminal, query(base + "&connect-timeout=invalid"), "connect-timeout")
    failed(terminal, query(base + "&connect-timeout=-1"), "connect-timeout")
    started = time.monotonic()
    terminal.command(query(uri("delayed", 0)))
    if time.monotonic() - started < 6:
        raise RuntimeError("disabled connection deadline did not allow delayed setup")
    _, log = build_project("longBuild", "--builders " + quote(base + "&connect-timeout=5"))
    if " on 'cpu://" not in log:
        raise RuntimeError("long build did not use the connected CPU")
    print("PASS: disabled setup deadlines allow slow handshakes; connected builds outlive the deadline", flush=True)

    retry = uri("retry")
    build.command("rm -f /tmp/cpu-setup-ready")
    timed_failure("nix-build /tmp/project -A timeout --no-out-link --builders " + quote(retry))
    build.command("echo ready > /tmp/cpu-setup-ready")
    result, _ = build_project("afterTimeout", "--builders " + quote(retry))
    terminal.command("cat " + result + "/builder", "build")
    print("PASS: connection timeout releases the builder slot for a subsequent build", flush=True)
    pool = uri("silent") + " x86_64-plan9 - 1 10 ; cpu://batch?key-pattern=dom%3Dnix9.builders x86_64-plan9 - 1 1"
    terminal.command("setupBuilders=" + quote(pool))
    result, log = build_project("timedFailover", "--builders $setupBuilders")
    if "connection setup timed out after 5 seconds" not in log:
        raise RuntimeError("fallback did not exercise a timed-out connection: " + log)
    terminal.command("cat " + result + "/builder", "batch")
    print("PASS: the same scheduling hook falls back after a timed-out connection", flush=True)
    return elapsed
