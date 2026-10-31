#include "nix/store/store-api.hh"
#include "nix/store/store-registration.hh"
#include "nix/store/serve-protocol-connection.hh"
#include "nix/store/serve-protocol-impl.hh"
#include "nix/store/globals.hh"
#include "nix/store/keys.hh"
#include "nix/util/archive.hh"
#include "nix/util/callback.hh"
#include "nix/util/executable-path.hh"
#include "nix/util/current-process.hh"
#include "nix/util/processes.hh"
#include "nix/util/strings.hh"
#include <mutex>

extern "C" long n9_rfork(int);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

struct CpuStoreConfig : virtual StoreConfig, std::enable_shared_from_this<CpuStoreConfig>
{
    explicit CpuStoreConfig(const Params & params) : StoreConfig(params) {
        if (!params.contains("store")) storeDir_.set("/usr/local/nix/store");
    }
    ParsedURL::Authority authority;
    CpuStoreConfig(const ParsedURL::Authority & authority, const Params & params)
        : CpuStoreConfig(params) { this->authority = authority; }
    Setting<std::string> keyPattern{this, "", "key-pattern", "Public factotum key-selection attributes."};
    Setting<std::string> remoteProgram{this, "nix-store", "remote-program", "Remote nix-store executable."};
    Setting<std::string> remoteStore{this, "", "remote-store", "Remote store URL; empty uses the CPU session's store."};
    Setting<int> logFD{this, 2, "log-fd", "Descriptor receiving remote build logs."};
    static std::string name() { return "CPU Store"; }
    static StringSet uriSchemes() { return {"cpu"}; }
    static std::string doc() { return "Nix serve protocol over authenticated 9front CPU sessions."; }
    ref<Store> openStore() const override;
    StoreReference getReference() const override {
        return {.variant = StoreReference::Specified{.scheme = "cpu", .authority = authority.to_string()},
                .params = getQueryParams()};
    }
};

// Commands pass through rc on both machines. Quote words using rc's doubled quote.
static std::string rcQuote(std::string_view word)
{
    std::string result = "'";
    for (char ch : word) result += ch == '\'' ? "''" : std::string(1, ch);
    return result + "'";
}

struct CpuStore : Store
{
    using Config = CpuStoreConfig;
    ref<const Config> config;
    struct Connection : ServeProto::BasicClientConnection {
        Pid pid;
        Pipe input, output;
        ~Connection() {
            // Closing the exported descriptors lets rcpu finish its session.
            input.writeSide.close();
            output.readSide.close();
        }
    };
    std::unique_ptr<Connection> connection;
    std::recursive_mutex connectionMutex;

    CpuStore(ref<const Config> config) : Store(*config), config(config) {}

    Connection & conn()
    {
        if (connection) return *connection;
        auto & authority = config->authority;
        if (authority.host.empty() || authority.host.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-") != std::string::npos)
            throw Error("cpu store requires a hostname or IPv4 address");
        if (config->keyPattern.get().find_first_of("\r\n!") != std::string::npos)
            throw Error("cpu store key-pattern must contain public factotum attributes only");
        auto host = authority.host;
        if (authority.port) host = "tcp!" + host + "!" + std::to_string(*authority.port);
        auto command = "exec " + rcQuote(config->remoteProgram.get()) + " --serve --write";
        if (!config->remoteStore.get().empty()) command += " --store " + rcQuote(config->remoteStore.get());
        auto rcpu = ExecutablePath::load().findPath("rcpu");
        auto script = "rfork n; bind /dev/null /dev/cons; bind /dev/null /dev/consctl; exec " + rcQuote(rcpu.string());
        if (authority.password) throw Error("cpu store passwords belong in factotum, outside store URLs");
        if (authority.user) script += " -u " + rcQuote(*authority.user);
        if (!config->keyPattern.get().empty()) script += " -k " + rcQuote(config->keyPattern.get());
        script += " -h " + rcQuote(host) + " -c " + rcQuote(command);
        auto rc = ExecutablePath::load().findPath("rc");
        auto next = std::make_unique<Connection>();
        next->input.create();
        next->output.create();
        next->pid = startProcess([&] {
            if (n9_rfork(1 << 3 /* RFNOTEG */) == -1)
                throw SysError(cc9_errno_from_errstr_or(EIO), "creating CPU client note group");
            if (dup2(next->input.readSide.get(), 0) == -1 || dup2(next->output.writeSide.get(), 1) == -1 ||
                dup2(config->logFD, 2) == -1)
                throw SysError("connecting CPU store pipes");
            restoreProcessContext();
            Strings args{"rc", "-e", "-c", script};
            execv(rc.c_str(), stringsToCharPtrs(args).data());
            throw SysError("starting CPU store connection");
        });
        // rcpu forwards interrupt to the remote command. A forced kill can
        // terminate nix-store before it unwinds and stops its builder group.
        next->pid.setKillSignal(SIGINT);
        next->input.readSide.close();
        next->output.writeSide.close();
        next->to = FdSink(next->input.writeSide.get());
        next->from = FdSource(next->output.readSide.get());
        try {
            next->remoteVersion = ServeProto::BasicClientConnection::handshake(
                next->to, next->from, ServeProto::latest, authority.host);
        } catch (Error & error) {
            error.addTrace({}, "while connecting to CPU store '%s'", config->getHumanReadableURI());
            throw;
        }
        connection = std::move(next);
        return *connection;
    }

    void connect() override { std::lock_guard lock(connectionMutex); conn(); }
    unsigned int getProtocol() override { std::lock_guard lock(connectionMutex); return conn().remoteVersion.toWire(); }
    std::optional<TrustedFlag> isTrustedClient() override { return Trusted; }

    void queryPathInfoUncached(const StorePath & path, Callback<std::shared_ptr<const ValidPathInfo>> callback) noexcept override {
        try {
            std::lock_guard lock(connectionMutex);
            auto infos = conn().queryPathInfos(*this, {path});
            auto found = infos.find(path);
            if (found == infos.end()) callback(nullptr);
            else callback(std::make_shared<ValidPathInfo>(path, std::move(found->second)));
        } catch (...) { callback.rethrow(); }
    }
    StorePathSet queryValidPaths(const StorePathSet & paths, SubstituteFlag substitute = NoSubstitute) override {
        std::lock_guard lock(connectionMutex);
        // Keep existing inputs alive until this authenticated session ends.
        return conn().queryValidPaths(*this, true, paths, substitute);
    }
    void addToStore(const ValidPathInfo & info, Source & source, RepairFlag repair, CheckSigsFlag checkSigs) override {
        std::lock_guard lock(connectionMutex);
        if (repair) unsupported("repairing CPU store paths");
        if (checkSigs && info.checkSignatures(*this, getDefaultPublicKeys()) == 0)
            throw Error("cannot copy unsigned path '%s' to a CPU store with signature checking", printStorePath(info.path));
        auto & c = conn();
        c.to << ServeProto::Command::AddToStoreNar << printStorePath(info.path)
             << (info.deriver ? printStorePath(*info.deriver) : "")
             << info.narHash.to_string(HashFormat::Base16, false);
        ServeProto::write(*this, c, info.references);
        c.to << info.registrationTime << info.narSize << info.ultimate;
        ServeProto::write(*this, c, info.sigs);
        c.to << renderContentAddress(info.ca);
        copyNAR(source, c.to);
        c.to.flush();
        if (readInt(c.from) != 1) throw Error("CPU store failed to import '%s'", printStorePath(info.path));
    }
    void narFromPath(const StorePath & path, Sink & sink) override {
        std::lock_guard lock(connectionMutex);
        conn().narFromPath(*this, path, [&](Source & source) { copyNAR(source, sink); });
    }
    void computeFSClosure(const StorePathSet & paths, StorePathSet & out, bool flip = false,
                         bool outputs = false, bool derivers = false) override {
        if (flip || derivers) return Store::computeFSClosure(paths, out, flip, outputs, derivers);
        std::lock_guard lock(connectionMutex);
        auto & c = conn();
        c.to << ServeProto::Command::QueryClosure << outputs;
        ServeProto::write(*this, c, paths);
        c.to.flush();
        auto result = ServeProto::Serialise<StorePathSet>::read(*this, c);
        out.insert(result.begin(), result.end());
    }
    BuildResult buildDerivation(const StorePath & path, const BasicDerivation & drv, BuildMode mode) override {
        std::lock_guard lock(connectionMutex);
        if (mode != bmNormal) unsupported("CPU store build modes other than normal");
        auto & worker = settings.getWorkerSettings();
        auto & c = conn();
        c.putBuildDerivationRequest(*this, path, drv, {
            .maxSilentTime = worker.maxSilentTime, .buildTimeout = worker.buildTimeout,
            .maxLogSize = worker.maxLogSize, .nrRepeats = 0, .enforceDeterminism = 0,
            .keepFailed = settings.keepFailed});
        return c.getBuildDerivationResponse(*this);
    }
    // The first transport supports the scheduler's buildDerivation path, not
    // remote evaluation, floating outputs, repair or a remote filesystem view.
    void buildPaths(const std::vector<DerivedPath> &, BuildMode, std::shared_ptr<Store>) override { unsupported("buildPaths"); }
    std::optional<StorePath> queryPathFromHashPart(const std::string &) override { unsupported("queryPathFromHashPart"); }
    StorePath addToStoreFromDump(Source &, std::string_view, FileSerialisationMethod, ContentAddressMethod,
                                HashAlgorithm, const StorePathSet &, RepairFlag) override { unsupported("addToStoreFromDump"); }
    void registerDrvOutput(const Realisation &) override { unsupported("registerDrvOutput"); }
    void queryRealisationUncached(const DrvOutput &, Callback<std::shared_ptr<const UnkeyedRealisation>> callback) noexcept override {
        try { unsupported("queryRealisation"); } catch (...) { callback.rethrow(); }
    }
    ref<SourceAccessor> getFSAccessor(bool) override { unsupported("getFSAccessor"); }
    std::shared_ptr<SourceAccessor> getFSAccessor(const StorePath &, bool) override { unsupported("getFSAccessor"); }
};

ref<Store> CpuStoreConfig::openStore() const { return make_ref<CpuStore>(ref{shared_from_this()}); }
static RegisterStoreImplementation<CpuStoreConfig> registerCpuStore;

}
