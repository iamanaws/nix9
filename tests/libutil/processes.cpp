#include "nix/util/processes.hh"
#include "nix/util/signals.hh"
#include "nix/util/muxable-pipe.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/file-system.hh"
#include "nix/store/pathlocks.hh"
#include <cstdlib>
#include <fcntl.h>
#include <sys/wait.h>
#include <iostream>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

int pathLockChild(std::string_view mode);
void checkFileCopies();

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

static void checkEnvironment() {
    const char *key = "NIX9_ENV_TEST";
    for (const auto &value : {std::string{}, std::string("first\nlast\n"), std::string(12000, 'x')}) {
        require(::setenv(key, value.c_str(), 1) == 0, "setenv failed");
        const char *actual = ::getenv(key);
        require(actual && value == actual, "getenv changed environment value");
        require(::setenv(key, "replacement", 0) == 0, "setenv without overwrite failed");
        actual = ::getenv(key);
        require(actual && value == actual, "setenv overwrote existing value");
        require(nix::getEnvOs().at(key) == value, "environment enumeration lost update");
    }
    nix::writeFile("/env/NIX9_ENV_TEST", std::string_view("direct\n\0", 8));
    require(std::string_view(::getenv(key)) == "direct\n", "getenv missed /env write");
    require(::unsetenv(key) == 0 && !::getenv(key), "unsetenv left a value");
    require(!nix::getEnvOs().contains(key), "environment enumeration retained removed value");
    for (const char *invalid : {"", ".", "..", "../dev/pid", "/dev/pid", "a=b"}) {
        require(!::getenv(invalid), "getenv accepted invalid name");
        require(::setenv(invalid, "x", 1) == -1 && errno == EINVAL, "setenv accepted invalid name");
        require(::unsetenv(invalid) == -1 && errno == EINVAL, "unsetenv accepted invalid name");
    }
    std::string longName(300, 'x');
    require(!::getenv(longName.c_str()), "getenv truncated name");
    require(::setenv(longName.c_str(), "x", 1) == -1 && errno == ENAMETOOLONG,
            "setenv truncated name");
}

static void checkExecPath() {
    using namespace nix;
    const std::filesystem::path root = "/tmp/nix9-path";
    std::filesystem::create_directories(root / "first");
    std::filesystem::create_directories(root / "second");
    for (auto [directory, status] : {std::pair{"first", 17}, {"second", 23}}) {
        auto script = root / directory / "command";
        writeFile(script, "#!/bin/rc\nexit 'cc9exit=" + std::to_string(status) + "'\n");
        require(::chmod(script.c_str(), 0755) == 0, "cannot make PATH fixture executable");
    }
    auto run = [&](const char *path, const char *program, int expected, int error = 0) {
        Pid child = startProcess([&] {
            if (::chdir(root.c_str()) != 0) _exit(98);
            if (path) ::setenv("PATH", path, 1); else ::unsetenv("PATH");
            char *args[] = {const_cast<char *>(program), nullptr};
            ::execvp(program, args);
            _exit(error && errno == error ? 0 : 99);
        });
        int status = child.wait();
        require(WIFEXITED(status) && WEXITSTATUS(status) == expected, "execvp PATH lookup failed");
    };
    run("first:second", "command", 17);
    run("second:first", "command", 23);
    run("missing:second", "command", 23);
    run("first/command:second", "command", 23); // Skip non-directory entries.
    run("missing", "first/command", 17); // Explicit paths bypass PATH.
    run("missing", "/tmp/nix9-path/second/command", 23);
    run("", "missing", 0, ENOENT);
    run("first:second", "", 0, ENOENT);
    run("missing", "cat", 0, ENOENT); // Do not fall back to /bin.
    run(nullptr, "echo", 0); // Native default when PATH is absent.
    writeFile(root / "command", "#!/bin/rc\nexit 'cc9exit=31'\n");
    require(::chmod((root / "command").c_str(), 0755) == 0, "cannot make local fixture executable");
    run("", "command", 31);
    run(":second", "command", 31);
    run("missing::second", "command", 31);
    run("missing:", "command", 31);
    std::string longPath;
    for (int i = 0; i < 100; ++i) longPath += "missing:";
    longPath += "second";
    run(longPath.c_str(), "command", 23);
    require(::chmod((root / "first/command").c_str(), 0644) == 0, "cannot prepare permission fixture");
    run("first:second", "command", 23);
    run("first:missing", "command", 0, EACCES);
    run("second", "first/command", 0, EACCES);
    deletePath(root);
}

static void checkNotes(int mode) {
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
                if (mode == 0) {
                    char byte;
                    readFull(blocked.readSide.get(), &byte, 1);
                } else {
                    std::optional<unsigned int> timeout = mode % 2 ? std::optional{3000u} : std::nullopt;
                    if (mode <= 2) {
                        struct pollfd fd{blocked.readSide.get(), POLLIN, 0};
                        int result = ::poll(&fd, 1, timeout ? *timeout : -1);
                        require(result == -1 && errno == EINTR, "poll swallowed interruption");
                    } else {
                        MuxablePipePollState state;
                        state.pollStatus.push_back({blocked.readSide.get(), POLLIN, 0});
                        state.poll(timeout);
                    }
                    checkInterrupt();
                }
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
        // Give the child time to enter the blocking wait before posting a note.
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
    checkFileCopies();
    checkEnvironment();
    checkExecPath();
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
    require(::poll(nullptr, 0, 0) == 0 && ::poll(nullptr, 0, 20) == 0,
            "empty poll did not time out");
    // Read, finite/infinite libc poll, then finite/infinite Nix poll.
    for (int mode = 0; mode < 5; ++mode) checkNotes(mode);
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
