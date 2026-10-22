#include "nix/store/local-store.hh"
#include "nix/store/store-open.hh"
#include "nix/util/current-process.hh"
#include "nix/util/util.hh"
#include <unistd.h>

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" void cc9_kill_threads(void);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

[[noreturn]] static void runRootedLauncher(LocalStore &store, const StorePath &output,
    const std::filesystem::path &root, const std::string &launcher, Strings arguments)
{
    if (!store.isValidPath(output))
        throw InvalidPath("cannot run invalid path '%s'", store.printStorePath(output));
    auto program = store.toRealPath(output) / launcher;
    if (!pathExists(program))
        throw Error("'%s' has no %s launcher", store.printStorePath(output), launcher);

    createDirs(root.parent_path());
    // The active store client excludes GC until this root is complete.
    // OWRITE | ORCLOSE | OEXCL, without OCEXEC: descendants inherit the root.
    // Exec closes the store's client marker, allowing GC during the session.
    AutoCloseFD rootFd(n9_create(root.c_str(), 1 | 64 | 0x1000, 0600));
    if (!rootFd) throw SysError(cc9_errno_from_errstr_or(EIO), "creating session root");
    writeFull(rootFd.get(), store.printStorePath(output) + '\n');

    Strings args{program.string()};
    args.splice(args.end(), arguments);
    auto argPtrs = stringsToCharPtrs(args);
    restoreProcessContext();
    logger->stop();
    // Native exec does not terminate cc9's sibling worker processes.
    cc9_kill_threads();
    execv(program.c_str(), argPtrs.data());
    throw SysError("executing launcher '%s'", program.string());
}

[[noreturn]] void runDevelopmentShell(LocalStore &store, const StorePath &output,
    const std::filesystem::path &root, const std::optional<std::string> &command)
{
    Strings args;
    if (command) args = {"-c", *command};
    runRootedLauncher(store, output, root, "shell", std::move(args));
}

[[noreturn]] void runEnvironmentSession(int argc, char **argv)
{
    if (argc < 1) throw UsageError("expected a store path for the environment session");
    auto store = openStore().dynamic_pointer_cast<LocalStore>();
    if (!store) throw UsageError("environment sessions require a local store");
    auto output = store->parseStorePath(argv[0]);
    auto root = makeTempPath(store->config->stateDir.get() / "gcroots", "nix-session");
    Strings args;
    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
    runRootedLauncher(*store, output, root, "session.rc", std::move(args));
}

}
