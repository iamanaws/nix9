#include "nix/store/build/derivation-builder.hh"
#include "nix/store/local-store.hh"
#include "nix/store/local-settings.hh"
#include "nix/store/posix-fs-canonicalise.hh"
#include "nix/store/path-references.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/current-process.hh"
#include "nix/util/file-system.hh"
#include "nix/util/signals.hh"
#include "build/derivation-check.hh"
#include <fcntl.h>
#include <unistd.h>

extern "C" long n9_rfork(int);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

class Plan9Builder : public DerivationBuilder, private DerivationBuilderParams {
    LocalStore &store;
    std::unique_ptr<DerivationBuilderCallbacks> callbacks;
    Pid pid;
    AutoCloseFD noteGroup;
    std::unique_ptr<AutoDelete> temp, output;
    std::optional<StorePath> outPath;
public:
    Plan9Builder(LocalStore &store, std::unique_ptr<DerivationBuilderCallbacks> callbacks,
                 DerivationBuilderParams params)
        : DerivationBuilderParams(std::move(params)), store(store), callbacks(std::move(callbacks)) {}
    ~Plan9Builder() override {
        try { killChild(); } catch (...) { ignoreExceptionInDestructor(); }
    }
    const StorePathSet &originalPaths() override { return inputPaths; }
    bool isAllowed(const StorePath &p) override { return inputPaths.contains(p); }
    bool isAllowed(const DrvOutput &) override { return false; }
    void addDependencyImpl(const StorePath &) override { throw Error("recursive builds are not supported on 9front"); }
    bool killChild() override {
        if (noteGroup) {
            // An open notepg file remembers the group even after its leader exits.
            writeFull(noteGroup.get(), "kill", false);
            noteGroup.close();
        }
        if (static_cast<pid_t>(pid) == -1) return false;
        pid.kill(false);
        return true;
    }
    std::optional<Descriptor> startBuild() override {
        if (buildMode != bmNormal || drv.outputs.size() != 1 || !drv.outputs.contains("out") ||
            !std::holds_alternative<DerivationOutput::InputAddressed>(drv.outputs.at("out").raw))
            throw Error("9front builds currently require one input-addressed output named 'out'");
        if (store.storeDir != store.config->realStoreDir.get())
            throw Error("building in a diverted store is not supported on 9front");
        if (store.config->getLocalSettings().sandboxMode != smDisabled)
            throw Error("sandboxed builds are not supported on 9front");
        if (!drvOptions.impureEnvVars.empty() || !drvOptions.impureHostDeps.empty() ||
            !drvOptions.additionalSandboxProfile.empty() || !drvOptions.unsafeDiscardReferences.empty())
            throw Error("unsupported 9front builder options");
        outPath = std::get<DerivationOutput::InputAddressed>(drv.outputs.at("out").raw).path;
        auto physical = store.toRealPath(*outPath);
        if (store.isValidPath(*outPath)) throw Error("refusing to replace a valid build output");
        deletePath(physical);
        output = std::make_unique<AutoDelete>(physical);
        auto directory = createTempDir("/tmp", "nix-build");
        temp = std::make_unique<AutoDelete>(directory);
        StringMap env{{"PATH", "/path-not-set"}, {"HOME", "/homeless-shelter"},
                      {"NIX_STORE", store.storeDir}, {"NIX_BUILD_TOP", directory.string()},
                      {"TMPDIR", directory.string()}, {"TMP", directory.string()},
                      {"TEMP", directory.string()}};
        for (auto &[name, value] : desugaredEnv.variables)
            env[name] = value.prependBuildDirectory ? (directory / value.value).string() : value.value;
        for (auto &[name, value] : desugaredEnv.extraFiles)
            writeFile(directory / name, value);
        env["out"] = store.printStorePath(*outPath);
        callbacks->openLogFile();
        Pipe log, ready, go;
        log.create();
        ready.create();
        go.create();
        pid = startProcess([&] {
            ready.readSide.close();
            go.writeSide.close();
            if (n9_rfork(1 << 3 /* RFNOTEG */) == -1)
                throw SysError(cc9_errno_from_errstr_or(EIO), "creating builder note group");
            writeFull(ready.writeSide.get(), "r");
            ready.writeSide.close();
            char byte;
            readFull(go.readSide.get(), &byte, 1);
            go.readSide.close();
            log.readSide.close();
            if (dup2(log.writeSide.get(), 1) == -1 || dup2(log.writeSide.get(), 2) == -1)
                throw SysError("redirecting builder output");
            AutoCloseFD input(open("/dev/null", O_RDONLY));
            if (!input || dup2(input.get(), 0) == -1 || chdir(directory.c_str()) == -1)
                throw SysError("preparing builder process");
            replaceEnv(env);
            Strings args(drv.args.begin(), drv.args.end());
            args.push_front(drv.builder);
            restoreProcessContext();
            execv(drv.builder.c_str(), stringsToCharPtrs(args).data());
            throw SysError("executing builder '%s'", drv.builder);
        });
        ready.writeSide.close();
        go.readSide.close();
        char byte;
        readFull(ready.readSide.get(), &byte, 1);
        auto groupPath = "/proc/" + std::to_string(static_cast<pid_t>(pid)) + "/notepg";
        noteGroup = AutoCloseFD(open(groupPath.c_str(), O_WRONLY | O_CLOEXEC));
        if (!noteGroup) throw SysError("opening builder note group");
        writeFull(go.writeSide.get(), "g");
        log.writeSide.close();
        builderOut = std::move(log.readSide);
        return builderOut.get();
    }
    SingleDrvOutputs unprepareBuild() override {
        int status = pid.wait();
        killChild();
        callbacks->childTerminated();
        callbacks->closeLogFile();
        if (!statusOk(status))
            throw BuilderFailureError{BuildResult::Failure::PermanentFailure, status, ""};
        auto physical = store.toRealPath(*outPath);
        if (!pathExists(physical)) throw BuildError(BuildResult::Failure::OutputRejected, "builder did not produce 'out'");
        canonicalisePathMetaData(physical, {});
        auto references = inputPaths;
        references.insert(*outPath);
        HashSink sink(HashAlgorithm::SHA256);
        auto found = scanForReferences(sink, physical, references);
        auto [hash, size] = sink.finish();
        ValidPathInfo info(*outPath, {store, hash});
        info.narSize = size;
        info.references = std::move(found);
        info.deriver = drvPath;
        info.ultimate = true;
        checkOutputs(store, drvPath, drv.outputs, drvOptions.outputChecks, {{"out", info}});
        store.signPathInfo(info);
        SingleDrvOutputs result;
        result.emplace("out", Realisation{{.outPath = *outPath}, DrvOutput{initialOutputs.at("out").outputHash, "out"}});
        store.registerValidPath(info);
        output->cancel();
        return result;
    }
};

void DerivationBuilderDeleter::operator()(DerivationBuilder *builder) noexcept { delete builder; }
DerivationBuilderUnique makeDerivationBuilder(LocalStore &store,
    std::unique_ptr<DerivationBuilderCallbacks> callbacks, DerivationBuilderParams params) {
    return DerivationBuilderUnique(new Plan9Builder(store, std::move(callbacks), std::move(params)));
}
DerivationBuilderUnique makeExternalDerivationBuilder(LocalStore &,
    std::unique_ptr<DerivationBuilderCallbacks>, DerivationBuilderParams, const ExternalBuilder &) {
    throw Error("external builders are not supported on 9front");
}
}
