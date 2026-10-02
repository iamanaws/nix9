#include "nix/store/pathlocks.hh"
#include "nix/util/file-system.hh"
#include "nix/util/processes.hh"
#include <iostream>
#include <unistd.h>
#include <sys/wait.h>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

static void execChild(const char *executable, const char *mode) {
    char *args[] = {const_cast<char *>(executable), const_cast<char *>("child"),
                    const_cast<char *>(mode), nullptr};
    ::execv(executable, args);
    _exit(99);
}

static const char *path = "/tmp/nix9-path-a";

int pathLockChild(std::string_view mode) {
    nix::PathLocks lock;
    if (mode == "lock-acquire") return lock.lockPaths({path}, "", false) ? 0 : 1;
    if (mode == "lock-try") {
        std::cout << (lock.lockPaths({path}, "", false) ? "acquired\n" : "busy\n");
        return 0;
    }
    if (mode == "lock-wait") {
        require(!lock.lockPaths({path}, "", false), "waiter did not encounter contention");
        nix::writeFull(1, "r");
        require(lock.lockPaths({path}), "blocking acquisition failed");
        nix::writeFull(1, "a");
        return 0;
    }
    return 2;
}

void checkPathLocks(const char *executable) {
    using namespace nix;
    auto available = [&] {
        return runProgram(executable, false, {"child", "lock-try"}) == "acquired\n";
    };
    auto marker = std::string(path) + ".lock";
    writeFile(marker, "stale");
    require(!available() && readFile(marker) == "stale", "existing marker was reclaimed or truncated");
    require(::unlink(marker.c_str()) == 0, "cannot remove test marker");
    PathLocks held;
    require(held.lockPaths({path}, "", false), "initial acquisition failed");
    require(!available(), "independent process bypassed lock");
    held.setDeletion(true);
    held.unlock();
    require(available(), "explicit unlock did not release lock");
    {
        PathLocks scoped({path});
        require(!available(), "constructor did not lock");
    }
    require(available(), "destructor did not release lock");

    // A failed multi-path acquisition must release earlier paths, including
    // when a constructor throws before its destructor can run.
    const char *later = "/tmp/nix9-path-b";
    held.lockPaths({later});
    PathLocks partial;
    require(!partial.lockPaths({path, later}, "", false), "partial acquisition bypassed lock");
    require(available(), "partial acquisition leaked lock");
    held.unlock();
    bool rejected = false;
    try { PathLocks broken({path, "/tmp/nix9-path-missing/child"}); }
    // cc9 maps an unrecognised native error to the supplied EIO fallback.
    catch (const SysError &e) { rejected = e.errNo == ENOENT || e.errNo == EIO; }
    require(rejected && available(), "creation error or constructor cleanup failed");

    rejected = false;
    try { partial.lockPaths({path, "/tmp/nix9-path-missing-exists/child"}, "", false); }
    catch (const SysError &e) { rejected = e.errNo != EEXIST; }
    require(rejected && available(), "filename was mistaken for lock contention");

    held.lockPaths({path});
    Pipe output;
    output.create();
    Pid waiter = startProcess([&] {
        output.readSide.close();
        require(::dup2(output.writeSide.get(), 1) == 1, "redirecting waiter failed");
        execChild(executable, "lock-wait");
    });
    output.writeSide.close();
    char byte;
    readFull(output.readSide.get(), &byte, 1);
    require(byte == 'r', "waiter did not start");
    ::usleep(250000);
    int status;
    require(::waitpid(static_cast<pid_t>(waiter), &status, WNOHANG) == 0,
            "blocking waiter exited while lock was held");
    held.unlock();
    readFull(output.readSide.get(), &byte, 1);
    require(byte == 'a' && statusOk(waiter.wait()), "waiter did not acquire released lock");

    Pipe ready;
    ready.create();
    Pid holder = startProcess([&] {
        ready.readSide.close();
        PathLocks lock({path});
        writeFull(ready.writeSide.get(), "r");
        for (;;) ::sleep(1);
    });
    ready.writeSide.close();
    readFull(ready.readSide.get(), &byte, 1);
    require(!available(), "child holder did not lock");
    require(!statusOk(holder.kill()) && available(), "killed holder leaked lock");

    // A fork retains the open marker even after the parent releases it.
    // Exec must close the inherited descriptor and allow reacquisition.
    held.lockPaths({path});
    Pipe proceed;
    proceed.create();
    Pid inherited = startProcess([&] {
        proceed.writeSide.close();
        readFull(proceed.readSide.get(), &byte, 1);
        execChild(executable, "lock-acquire");
    });
    proceed.readSide.close();
    held.unlock();
    require(!available(), "fork did not retain lock");
    writeFull(proceed.writeSide.get(), "r");
    require(statusOk(inherited.wait()) && available(), "exec retained inherited lock");
    require(!std::filesystem::exists(std::string(path) + ".lock"), "lock marker remained");
}
