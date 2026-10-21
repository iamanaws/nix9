"""Fetch pinned Git commits with native tools and verify exported source trees."""

import functools
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from guest import boot


class GitHandler(http.server.SimpleHTTPRequestHandler):
    def backend(self):
        request = urlsplit(self.path)
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                size = int(self.rfile.readline().split(b";", 1)[0], 16)
                if size == 0:
                    while self.rfile.readline().strip():
                        pass
                    break
                chunks.append(self.rfile.read(size))
                if self.rfile.read(2) != b"\r\n":
                    raise RuntimeError("invalid HTTP chunk")
            body = b"".join(chunks)
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        environment = os.environ | {
            "GIT_PROJECT_ROOT": self.directory,
            "GIT_HTTP_EXPORT_ALL": "1",
            "REQUEST_METHOD": self.command,
            "PATH_INFO": request.path,
            "QUERY_STRING": request.query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_ADDR": "127.0.0.1",
        }
        response = subprocess.check_output(["git", "http-backend"], input=body, env=environment)
        headers, separator, content = response.partition(b"\r\n\r\n")
        if not separator:
            raise RuntimeError("invalid Git CGI response")
        headers = dict(line.decode("latin1").split(": ", 1) for line in headers.split(b"\r\n"))
        self.send_response(int(headers.pop("Status", "200 OK").split()[0]))
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path.startswith("/repo.git/"):
            self.backend()
        else:
            super().do_GET()

    def do_POST(self):
        self.backend()


def rooted(guest, path):
    result = guest.command(f"cat {path}")
    paths = re.findall(r"(?m)^/usr/local/nix/store/[^\s]+$", result)
    if len(paths) != 1:
        raise RuntimeError(f"missing output: {result}")
    return paths[0]


qemu, image, bootstrap, output = sys.argv[1:]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    repo = root / "work"
    repo.mkdir()
    environment = os.environ | {
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.org", "GIT_COMMITTER_EMAIL": "fixture@example.org",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    }

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(repo), *arguments], env=environment, text=True).strip()

    git("init", "-b", "main")
    (repo / "main.c").write_text('#include <u.h>\n#include <libc.h>\nvoid main(void) { print("pinned Git source PASS\\n"); exits(nil); }\n')
    (repo / ".hidden").write_text("hidden\n")
    (repo / "empty").touch()
    (repo / "payload").write_bytes(bytes(range(256)) * 512)
    (repo / "nested dir").mkdir()
    (repo / "nested dir/it's here").write_text("names are preserved\n")
    (repo / "run.rc").write_text("#!/bin/rc\necho executable-Git-source-PASS\n")
    (repo / "run.rc").chmod(0o755)
    git("add", ".")
    git("commit", "-m", "source")
    revision = git("rev-parse", "HEAD")
    expected = root / "expected"
    shutil.copytree(repo, expected, ignore=shutil.ignore_patterns(".git"))
    digest = subprocess.check_output(["nix", "--extra-experimental-features", "nix-command", "hash", "path", str(expected)], text=True).strip()
    (repo / "main.c").write_text("this is the moving branch tip, not the requested commit\n")
    git("commit", "-am", "move branch")
    git("checkout", "-b", "links", revision)
    (repo / "link").symlink_to("main.c")
    git("add", "link")
    git("commit", "-m", "symlink")
    link_revision = git("rev-parse", "HEAD")
    git("checkout", "-b", "modules", revision)
    git("update-index", "--add", "--cacheinfo", f"160000,{revision},module")
    git("commit", "-m", "submodule")
    module_revision = git("rev-parse", "HEAD")
    git("checkout", "main")
    subprocess.run(["git", "clone", "--bare", str(repo), str(root / "repo.git")], env=environment, check=True)
    (root / "bootstrap.tar").symlink_to(Path(bootstrap).resolve())
    (root / "git.nix").symlink_to(Path(__file__).with_name("git.nix"))
    handler = functools.partial(GitHandler, directory=directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with boot(qemu, image) as guest:
                guest.child.timeout = 600
                base = f"http://10.0.2.2:{server.server_port}"
                for name in ("bootstrap.tar", "git.nix"):
                    guest.command(f"hget -o /tmp/{name} {base}/{name}")
                guest.command("cd / && tar xf /tmp/bootstrap.tar")
                guest.command(". /usr/local/pkg/nix9/activate")
                roots = "/usr/local/nix/state/gcroots"
                guest.command(f"nix-build $nix9/shell.nix --out-link {roots}/toolchain")
                guest.command("NIX_CONFIG='substituters ='")
                guest.command(f"url={base}/repo.git; rev={revision}; hash='{digest}'")
                guest.command("fn gitBuild { nix-build /tmp/git.nix --argstr packages $nix9/packages --argstr url $url --argstr rev $rev --argstr hash $hash $* }")
                guest.command(f"gitBuild -A source --out-link {roots}/git-source")
                source = rooted(guest, roots + "/git-source")
                guest.command(f"test ! -e {source}/.git")
                guest.command(f"{source}/run.rc", "executable-Git-source-PASS")
                guest.command(f"gitBuild -A hello --out-link {roots}/git-hello")
                hello = rooted(guest, roots + "/git-hello")
                guest.command(f"{hello}/bin/hello", "pinned Git source PASS")
                for name in ("libflate", "git"):
                    guest.command(f"nix-build '<nix9>' -A {name} --check --no-out-link")
                guest.command("hash='sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='")
                for commit, reason in ((revision, "hash mismatch"), ("0" * 40, "expected commit"),
                                       (link_revision, "unsupported symlink or submodule"),
                                       (module_revision, "unsupported symlink or submodule")):
                    guest.command(f"rev={commit}")
                    result = guest.command(f"gitBuild -A source --out-link {roots}/rejected; echo FETCH-STATUS:$status")
                    if reason not in result or not re.search(r"(?m)^FETCH-STATUS:.+", result):
                        raise RuntimeError(f"Git fetch was not rejected ({reason}): {result}")
                for commit in ("HEAD", "main", revision[:12]):
                    guest.command(f"rev={commit}")
                    result = guest.command("gitBuild -A source --no-out-link; echo FETCH-STATUS:$status")
                    if "assertion" not in result or not re.search(r"(?m)^FETCH-STATUS:.+", result):
                        raise RuntimeError(f"unpinned revision was accepted: {result}")
                server.shutdown()
                thread.join()
                guest.command(f"url={base}/offline.git; rev={revision}; hash='{digest}'")
                guest.command(f"gitBuild -A source --out-link {roots}/git-source", source)
                guest.command(f"nix-store --verify-path {source}")
        finally:
            server.shutdown()
            thread.join()

Path(output).mkdir()
Path(output, "results.json").write_text(json.dumps({
    "fetchgit": "pinned commit, exact tree hash, executable bits, native consumer, rejected modes and offline reuse passed",
}, indent=2) + "\n")
