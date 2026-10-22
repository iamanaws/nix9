#include "nix/store/local-store.hh"
#include "nix/store/store-open.hh"
#include "nix/store/derivations.hh"
#include "nix/store/derivation-options.hh"
#include "nix/store/globals.hh"
#include "nix/util/current-process.hh"
#include "nix/util/util.hh"
#include <unistd.h>

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" void cc9_kill_threads(void);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

[[noreturn]] static void runRootedProgram(LocalStore &store, const StorePath &output,
    const std::filesystem::path &root, const std::filesystem::path &program, Strings arguments)
{
    if (!store.isValidPath(output))
        throw InvalidPath("cannot run invalid path '%s'", store.printStorePath(output));
    if (!pathExists(program))
        throw Error("launcher '%s' does not exist", PathFmt(program));

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

[[noreturn]] void runDevelopmentShell(LocalStore &store, const Derivation &drv,
    const StorePathSet &inputs, const std::filesystem::path &directory,
    const std::filesystem::path &root, const std::optional<std::string> &command)
{
    auto setup = drv.env.find("__nix9ShellSetup");
    if (setup == drv.env.end())
        throw UsageError("derivation has no rc shell setup; use stdenv.mkDerivation");
    if (drv.structuredAttrs)
        throw UsageError("structured shell environments are not supported");
    auto quote = [](std::string_view value) {
        return "'" + replaceStrings(std::string(value), "'", "''") + "'";
    };
    const auto &tools = drv.env.at("tools");
    auto options = derivationOptionsFromStructuredAttrs(store, drv.env, get(drv.structuredAttrs));
    auto env = drv.env;
    env.erase("__nix9ShellSetup");
    unsigned fileNr = 0;
    for (const auto &name : options.passAsFile) {
        auto value = env.find(name);
        if (value == env.end()) continue;
        auto path = directory / (".attr-" + std::to_string(fileNr++));
        writeFile(path, value->second);
        env[name + "Path"] = path.string();
        env.erase(value);
    }
    for (auto name : {"NIX_BUILD_TOP", "TMPDIR", "TEMPDIR", "TMP", "TEMP"})
        env[name] = directory.string();
    env["NIX_STORE"] = store.storeDir;
    env["NIX_BUILD_CORES"] = std::to_string(
        settings.getLocalSettings().buildCores ? settings.getLocalSettings().buildCores : settings.getDefaultCores());
    env["IN_NIX_SHELL"] = "impure";
    std::string script = "rfork ne\nflag e +\nfn sigexit {\n"
        "  nix9ShellStatus=$status\n  " + quote(tools + "/bin/rm") + " -rf " + quote(directory.string()) +
        "\n  exit $nix9ShellStatus\n}\n";
    for (const auto &[name, value] : env)
        script += quote(name) + "=" + quote(value) + "\n";
    script += setup->second + "\n";
    if (auto hook = env.find("shellHook"); hook != env.end()) script += hook->second + "\n";
    auto shell = quote(drv.builder) + " -m " + quote(tools + "/rcmain");
    script += "flag e -\nfn sigint {}\nif(~ $#* 0) " + shell + " -i\nif not " + shell + " $*\nexit $status\n";
    StringSource source(script);
    auto launcher = store.addToStoreFromDump(source, "nix-shell", FileSerialisationMethod::Flat,
        ContentAddressMethod::Raw::Text, HashAlgorithm::SHA256, inputs, NoRepair);
    Strings args{"-m", tools + "/rcmain", "-e", store.printStorePath(launcher)};
    if (command) args.insert(args.end(), {"-c", *command});
    runRootedProgram(store, launcher, root, drv.builder, std::move(args));
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
    runRootedProgram(*store, output, root, store->toRealPath(output) / "session.rc", std::move(args));
}

}
