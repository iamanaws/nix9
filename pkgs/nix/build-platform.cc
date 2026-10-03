#include "nix/store/build/derivation-builder.hh"
#include "nix/store/local-store.hh"
#include "nix/store/local-settings.hh"
#include "nix/store/posix-fs-canonicalise.hh"
#include "nix/store/path-references.hh"
#include "nix/store/references.hh"
#include "nix/util/archive.hh"
#include "nix/util/util.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/current-process.hh"
#include "nix/util/file-system.hh"
#include "nix/util/source-path.hh"
#include "nix/util/posix-source-accessor.hh"
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
    std::unique_ptr<AutoDelete> temp;
    std::map<std::string, std::unique_ptr<AutoDelete>> cleanupOutputs;
    OutputPathMap outputPaths, scratchOutputs;
    StringMap inputRewrites, outputRewrites;
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
        if (buildMode != bmNormal)
            throw Error("only normal builds are supported on 9front");
        for (auto &[name, output] : drv.outputs) {
            if (auto fixed = std::get_if<DerivationOutput::CAFixed>(&output.raw)) {
                if (fixed->ca.method != ContentAddressMethod::Raw::Flat &&
                    fixed->ca.method != ContentAddressMethod::Raw::NixArchive)
                    throw Error("9front fixed-output builds require flat or recursive hashing");
            } else if (!std::holds_alternative<DerivationOutput::InputAddressed>(output.raw))
                throw Error("9front builds require input-addressed or fixed outputs");
            outputPaths.emplace(name, *output.path(store, drv.name, name));
        }
        if (store.storeDir != store.config->realStoreDir.get())
            throw Error("building in a diverted store is not supported on 9front");
        if (store.config->getLocalSettings().sandboxMode != smDisabled)
            throw Error("sandboxed builds are not supported on 9front");
        if (!drvOptions.impureEnvVars.empty() || !drvOptions.impureHostDeps.empty() ||
            !drvOptions.additionalSandboxProfile.empty() || !drvOptions.unsafeDiscardReferences.empty())
            throw Error("unsupported 9front builder options");
        auto directory = createTempDir("/tmp", "nix-build");
        temp = std::make_unique<AutoDelete>(directory);
        for (auto &[name, path] : outputPaths) {
            auto scratch = path;
            if (store.isValidPath(path)) {
                // Like upstream's unsandboxed builder, redirect retained outputs
                // and rewrite their hashes back in the newly produced outputs.
                scratch = store.makeStorePath(
                    "rewrite:" + std::string(drvPath.to_string()) + ":" + std::string(path.to_string()),
                    Hash(HashAlgorithm::SHA256), path.name());
                inputRewrites[std::string(path.hashPart())] = std::string(scratch.hashPart());
                outputRewrites[std::string(scratch.hashPart())] = std::string(path.hashPart());
            }
            if (store.isValidPath(scratch)) throw Error("refusing to replace a valid build output");
            inputRewrites[hashPlaceholder(name)] = store.printStorePath(scratch);
            store.addTempRoot(scratch);
            auto physical = store.toRealPath(scratch);
            deletePath(physical);
            cleanupOutputs.emplace(name, std::make_unique<AutoDelete>(physical));
            scratchOutputs.emplace(name, scratch);
        }
        StringMap env{{"PATH", "/path-not-set"}, {"HOME", "/homeless-shelter"},
                      {"NIX_STORE", store.storeDir}, {"NIX_BUILD_TOP", directory.string()},
                      {"TMPDIR", directory.string()}, {"TMP", directory.string()},
                      {"TEMP", directory.string()}};
        for (auto &[name, value] : desugaredEnv.variables)
            env[name] = value.prependBuildDirectory ? (directory / value.value).string() : value.value;
        for (auto &[name, value] : desugaredEnv.extraFiles)
            writeFile(directory / name, rewriteStrings(value, inputRewrites));
        for (auto &[name, path] : scratchOutputs)
            env[name] = store.printStorePath(path);
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
            for (auto &[name, value] : env) value = rewriteStrings(value, inputRewrites);
            replaceEnv(env);
            Strings args;
            for (auto &arg : drv.args) args.push_back(rewriteStrings(arg, inputRewrites));
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
        auto references = inputPaths;
        for (auto &[name, path] : outputPaths) references.insert(path);
        std::map<std::string, ValidPathInfo> infos;
        ValidPathInfos registrations;
        SingleDrvOutputs result;
        for (auto &[name, path] : outputPaths) {
            auto scratch = scratchOutputs.at(name);
            if (scratch != path) {
                // Never replace the contents or metadata of an already valid output.
                infos.emplace(name, *store.queryPathInfo(path));
            } else {
                auto physical = store.toRealPath(path);
                if (!pathExists(physical))
                    throw BuildError(BuildResult::Failure::OutputRejected, "builder did not produce '%s'", name);
                if (!outputRewrites.empty()) {
                    auto source = sinkToSource([&](Sink &sink) {
                        RewritingSink rewriting(outputRewrites, sink);
                        dumpPath(physical, rewriting);
                        rewriting.flush();
                    });
                    auto rewritten = physical.string() + ".tmp";
                    AutoDelete cleanup(rewritten);
                    restorePath(rewritten, *source);
                    deletePath(physical);
                    std::filesystem::rename(rewritten, physical);
                }
                canonicalisePathMetaData(physical, {});
                HashSink sink(HashAlgorithm::SHA256);
                auto found = scanForReferences(sink, physical, references);
                auto [hash, size] = sink.finish();
                ValidPathInfo info(path, {store, hash});
                info.narSize = size;
                info.references = std::move(found);
                if (auto fixed = std::get_if<DerivationOutput::CAFixed>(&drv.outputs.at(name).raw)) {
                    auto method = fixed->ca.method.getFileIngestionMethod();
                    if (method == FileIngestionMethod::Flat) {
                        auto st = lstat(physical);
                        if (!S_ISREG(st.st_mode) || (st.st_mode & S_IXUSR))
                            throw BuildError(BuildResult::Failure::OutputRejected,
                                "flat fixed-output builds require a non-executable regular file");
                    }
                    auto content = hashPath(
                        {getFSSourceAccessor(), CanonPath(physical.string())},
                        static_cast<FileSerialisationMethod>(method), fixed->ca.hash.algo);
                    info.ca = ContentAddress{fixed->ca.method, content.hash};
                }
                info.deriver = drvPath;
                info.ultimate = true;
                infos.emplace(name, info);
                store.signPathInfo(info);
                registrations.emplace(path, std::move(info));
            }
            result.emplace(name, Realisation{{.outPath = path}, DrvOutput{initialOutputs.at(name).outputHash, name}});
        }
        checkOutputs(store, drvPath, drv.outputs, drvOptions.outputChecks, infos);
        // All outputs and their references become valid in one transaction.
        store.registerValidPaths(registrations);
        for (auto &[name, path] : outputPaths)
            if (scratchOutputs.at(name) == path) cleanupOutputs.at(name)->cancel();
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
