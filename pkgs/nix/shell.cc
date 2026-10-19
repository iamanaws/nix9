#include "nix/store/local-store.hh"
#include "nix/util/current-process.hh"
#include "nix/util/util.hh"
#include <unistd.h>

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" void cc9_kill_threads(void);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

[[noreturn]] void runDevelopmentShell(LocalStore &store, const StorePath &output,
    const std::filesystem::path &root, const std::optional<std::string> &command)
{
    auto shell = store.toRealPath(output) / "shell";
    if (!pathExists(shell))
        throw Error("'%s' has no mkShell launcher", store.printStorePath(output));

    createDirs(root.parent_path());
    // The active store client excludes GC until this root is complete.
    // OWRITE | ORCLOSE | OEXCL, without OCEXEC: the shell inherits the root.
    // Exec closes the store's client marker, allowing GC during the session.
    AutoCloseFD rootFd(n9_create(root.c_str(), 1 | 64 | 0x1000, 0600));
    if (!rootFd) throw SysError(cc9_errno_from_errstr_or(EIO), "creating shell root");
    writeFull(rootFd.get(), store.printStorePath(output) + '\n');

    Strings args{shell.string()};
    if (command) {
        args.push_back("-c");
        args.push_back(*command);
    }
    auto argPtrs = stringsToCharPtrs(args);
    restoreProcessContext();
    logger->stop();
    // Native exec does not terminate cc9's sibling worker processes.
    cc9_kill_threads();
    execv(shell.c_str(), argPtrs.data());
    throw SysError("executing development shell '%s'", shell.string());
}

}
