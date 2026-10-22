"""Compare native, cross-compiled, and mixed-compiler C objects in 9front."""

import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

from guest import boot


EXPECTED = [
    "PASS: arguments and data model",
    "PASS: integer calls and recursion",
    "PASS: pointers and callbacks",
    "PASS: structures by value and return",
    "PASS: floating point",
    "PASS: varargs and libc calls",
]


def main():
    qemu, disk, sources, cross, output_dir, *toolchain = sys.argv[1:]
    results = {}
    with tempfile.TemporaryDirectory() as directory:
        for name in ("main.c", "callee.c", "abi.h"):
            shutil.copyfile(Path(sources) / name, Path(directory) / name)
        for name in ("main.6", "callee.6", "abi-tests"):
            shutil.copyfile(Path(cross) / name, Path(directory) / name)
        if toolchain:
            for name in ("6a", "6c", "6l", "cpp", "pcc"):
                shutil.copyfile(Path(toolchain[0]) / "bin" / name, Path(directory) / name)
            Path(directory, "answer.s").write_text("TEXT answer(SB), 1, $0\nMOVL $42, AX\nRET\n")
            Path(directory, "answer.c").write_text(
                '#include <u.h>\n#include <libc.h>\nint answer(void);\n'
                'void main(void) { assert(answer() == 42); exits(nil); }\n'
            )
            Path(directory, "ape.c").write_text(
                '#include <stdio.h>\n#if ANSWER != 42\n#error wrong macro\n#endif\n'
                'int main(void) { puts("APE compiler PASS"); return 0; }\n'
            )
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with boot(qemu, disk) as guest:
                    url = f"http://10.0.2.2:{server.server_port}"
                    guest.command("mkdir /tmp/abi")
                    if toolchain:
                        for name in ("6a", "6c", "6l", "cpp", "pcc", "answer.s", "answer.c", "ape.c"):
                            guest.command(f"hget -o /tmp/abi/{name} {url}/{name}")
                        for name in ("6a", "6c", "6l", "cpp", "pcc"):
                            guest.command(f"chmod +x /tmp/abi/{name}; bind /tmp/abi/{name} /bin/{name}")
                    for name in ("main.c", "callee.c", "abi.h", "main.6", "callee.6", "abi-tests"):
                        guest.command(f"hget -o /tmp/abi/{name} {url}/{name}")
                    guest.command("cd /tmp/abi && 6c -o native-main.6 main.c")
                    guest.command("cd /tmp/abi && 6c -o native-callee.6 callee.c")
                    combinations = {
                        "native": "native-main.6 native-callee.6",
                        "cross-caller": "main.6 native-callee.6",
                        "native-caller": "native-main.6 callee.6",
                    }
                    for name, objects in combinations.items():
                        guest.command(f"cd /tmp/abi && 6l -o {name} {objects}")
                    guest.command("chmod +x /tmp/abi/abi-tests")
                    for name in ("native", "cross-caller", "native-caller", "abi-tests"):
                        output = guest.command(f"/tmp/abi/{name} alpha 23")
                        lines = [line for line in output.splitlines() if line.startswith("PASS:")]
                        if lines != EXPECTED:
                            raise RuntimeError(f"{name}: unexpected results: {lines!r}")
                        results[name] = lines
                    if toolchain:
                        guest.command("cd /tmp/abi && 6a -o assembly.6 answer.s && 6c -o answer.6 answer.c")
                        guest.command("6l -o answer answer.6 assembly.6 && ./answer")
                        result = guest.command("echo invalid > invalid.c; 6c invalid.c; echo CC-STATUS:$status")
                        if not any(line.startswith("CC-STATUS:") and line != "CC-STATUS:" for line in result.splitlines()):
                            raise RuntimeError("compiler accepted invalid C")
                        results["assembler"] = "assembly linked with C and returned 42"
                        guest.command("pcc '-DANSWER=42' -o ape ape.c && ./ape", "APE compiler PASS")
                        results["ape"] = "source-built preprocessor and compiler driver passed"
            finally:
                server.shutdown()
    destination = Path(output_dir)
    destination.mkdir(parents=True)
    (destination / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("\nPASS: 6 ABI groups agree across native, cross, and both mixed builds")


if __name__ == "__main__":
    main()
