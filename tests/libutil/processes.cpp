#include "nix/util/processes.hh"
#include "nix/util/signals.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/file-system.hh"
#include "nix/store/pathlocks.hh"
#include <fcntl.h>
#include <sys/wait.h>
#include <iostream>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

int pathLockChild(std::string_view mode);

int processChild(int argc, char **argv) {
    std::string_view mode = argv[2];
    if (mode.starts_with("lock-")) return pathLockChild(mode);
    if (mode == "echo") {
        char bytes[4096];
        ssize_t n;
        while ((n = ::read(0, bytes, sizeof bytes)) > 0)
            nix::writeFull(1, std::string_view(bytes, n));
        return n < 0 ? 1 : 0;
    }
    if (mode == "exit") return 42;
    if (mode == "context") {
        require(argc == 5 && std::string_view(argv[3]) == "a b'\"$", "argument changed");
        require(nix::getEnv("NIX9_PROCESS") == "child value", "missing child environment");
        require(nix::getEnv("NIX9_EMPTY") == "", "lost empty environment value");
        require(nix::getEnv("NIX9_LINES") == "first\nlast\n", "changed environment newlines");
        require(!nix::getEnv("NIX9_PARENT"), "inherited excluded environment");
        require(std::filesystem::current_path() == "/tmp/nix9-process-dir", "wrong child directory");
        struct stat st;
        require(::fstat(std::stoi(argv[4]), &st) == -1 && errno == EBADF, "close-on-exec descriptor leaked");
        nix::writeFull(1, "stdout\n");
        nix::writeFull(2, "stderr\n");
        return 0;
    }
    return 2;
}

static void checkNotes() {
    using namespace nix;
    Pipe ready, blocked;
    ready.create();
    blocked.create();
    const std::filesystem::path scratch = "/tmp/nix9-note-cleanup";
    Pid child = startProcess([&] {
        unix::startNoteHandler();
        ready.readSide.close();
        blocked.writeSide.close();
        for (int i = 0; i < 2; ++i) {
            bool interrupted = false;
            try {
                writeFile(scratch, "unfinished");
                AutoDelete cleanup(scratch);
                writeFull(ready.writeSide.get(), "r");
                char byte;
                readFull(blocked.readSide.get(), &byte, 1);
            } catch (const Interrupted &) {
                interrupted = true;
            }
            setInterrupted(false);
            if (!interrupted || pathExists(scratch)) _exit(11);
        }
        _exit(0);
    });
    ready.writeSide.close();
    blocked.readSide.close();
    for (const char *note : {"interrupt", "hangup"}) {
        char byte;
        readFull(ready.readSide.get(), &byte, 1);
        // Give the child time to enter the blocking read before posting a note.
        usleep(100000);
        auto path = "/proc/" + std::to_string(static_cast<pid_t>(child)) + "/note";
        AutoCloseFD fd(::open(path.c_str(), O_WRONLY));
        require(fd.get() >= 0, "cannot open child note file");
        writeFull(fd.get(), note);
    }
    require(statusOk(child.wait()), "note cancellation or cleanup failed");
    require(!getInterrupted(), "child note interrupted parent");
}

void checkProcesses(const char *executable) {
    using namespace nix;
    require(!getEnv("/dev/pid") && !getEnv("../dev/pid"), "environment name escaped /env");
    std::string payload;
    for (int i = 0; i < 131073; ++i) payload += static_cast<char>(i);
    require(runProgram(executable, false, {"child", "echo"}, payload) == payload,
            "duplex pipe transfer failed");
    require(runProgram("/bin/cat", false, {}, payload) == payload, "native cat transfer failed");
    auto failed = runProgram(RunOptions{.program=executable, .args={"child", "exit"}});
    require(WIFEXITED(failed.first) && WEXITSTATUS(failed.first) == 42, "lost exit status");
    bool rejected = false;
    try { runProgram(executable, false, {"child", "exit"}); }
    catch (const ExecError &e) { rejected = WIFEXITED(e.status) && WEXITSTATUS(e.status) == 42; }
    require(rejected, "failed child accepted");
    auto missing = runProgram(RunOptions{.program="/tmp/no-such-nix9-program", .mergeStderrToStdout=true});
    require(!statusOk(missing.first) && missing.second.find("executing") != std::string::npos,
            "failed exec accepted");

    auto cwd = std::filesystem::current_path();
    setEnv("NIX9_PARENT", "parent value");
    AutoCloseFD fd(::open("/dev/null", O_RDONLY));
    require(fd.get() >= 0, "cannot prepare inherited descriptor");
    unix::closeOnExec(fd.get());
    auto context = runProgram(RunOptions{
        .program=std::filesystem::path(executable).filename(),
        .args={"child", "context", "a b'\"$", std::to_string(fd.get())}, .chdir="/tmp/nix9-process-dir",
        .environment=OsStringMap{{"PATH", "/missing:/tmp"}, {"NIX9_PROCESS", "child value"},
                                {"NIX9_EMPTY", ""}, {"NIX9_LINES", "first\nlast\n"}},
        .mergeStderrToStdout=true});
    require(statusOk(context.first) && context.second == "stdout\nstderr\n", "child context failed");
    require(getEnv("NIX9_PARENT") == "parent value" && std::filesystem::current_path() == cwd,
            "child changed parent context");

    // Wait for children in reverse order, then kill and reap a live child.
    Pid first = startProcess([] { _exit(17); });
    Pid second = startProcess([] { _exit(23); });
    int b = second.wait(), a = first.wait();
    require(WIFEXITED(a) && WEXITSTATUS(a) == 17 && WIFEXITED(b) && WEXITSTATUS(b) == 23,
            "wait returned another child's status");
    Pipe ready;
    ready.create();
    Pid sleeper = startProcess([&] {
        ready.readSide.close();
        writeFull(ready.writeSide.get(), "r");
        for (;;) ::sleep(1);
    });
    ready.writeSide.close();
    char byte;
    readFull(ready.readSide.get(), &byte, 1);
    auto pid = static_cast<pid_t>(sleeper);
    require(!statusOk(sleeper.kill()), "killed child reported success");
    int status;
    require(waitpid(pid, &status, WNOHANG) == -1 && errno == ECHILD, "child not reaped");

    for (bool group : {false, true}) {
        RunOptions options{.program=executable, .args={"child", "exit"}};
        if (group) options.gid = 1; else options.uid = 1;
        rejected = false;
        try { runProgram2(options); }
        catch (const Error &e) {
            rejected = std::string_view(e.what()).find("credentials") != std::string_view::npos;
        }
        require(rejected, "unsupported credentials accepted");
    }
    Pid unassigned;
    rejected = false;
    try { unassigned.setSeparatePG(true); }
    catch (const Error &) { rejected = true; }
    require(rejected, "unsupported process group accepted");
    rejected = false;
    try { killUser(1); }
    catch (const Error &) { rejected = true; }
    require(rejected, "unsupported user termination accepted");
    checkNotes();
}

void checkLocks() {
    auto fd = nix::openLockFile("/tmp/nix9-lock", true);
    for (auto type : {nix::ltRead, nix::ltWrite}) {
        for (bool wait : {false, true}) {
            bool rejected = false;
            try { nix::lockFile(fd.get(), type, wait); }
            catch (const nix::SysError &e) { rejected = e.errNo == ENOLCK; }
            require(rejected, "unsupported file lock reported success");
        }
    }
}
