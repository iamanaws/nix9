#include "nix/store/remote-store.hh"
#include "nix/store/remote-store-connection.hh"
#include "nix/store/worker-protocol-impl.hh"
#include "nix/store/local-fs-store.hh"
#include "nix/store/store-registration.hh"
#include "nix/store/plan9-roots.hh"
#include "nix/util/current-process.hh"
#include "nix/util/executable-path.hh"
#include "nix/util/processes.hh"
#include "nix/util/strings.hh"

extern "C" long n9_rfork(int);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

// cc9 gives each thread a kernel PID. Record the process before threads start,
// so a connection opened by a short-lived worker still follows the client.
static const pid_t clientProcess = getpid();

struct Plan9DaemonConfig : LocalFSStoreConfig, RemoteStoreConfig,
    std::enable_shared_from_this<Plan9DaemonConfig>
{
    explicit Plan9DaemonConfig(const Params & params)
        : StoreConfig(params), LocalFSStoreConfig(params), RemoteStoreConfig(params)
    {
        if (!params.contains("store")) storeDir_.set("/usr/local/nix/store");
        if (!params.contains("real")) realStoreDir.set(std::filesystem::path{storeDir});
    }
    Plan9DaemonConfig(std::string_view, std::string_view authority, const Params & params)
        : Plan9DaemonConfig(params)
    {
        if (!authority.empty()) throw Error("use daemon?address=... for native daemon connections");
    }
    Setting<std::string> address{this, "tcp!127.0.0.1!17051", "address", "Native authenticated store-service address."};
    Setting<std::string> keyPattern{this, "", "key-pattern", "Public factotum key-selection attributes."};
    static std::string name() { return "Plan 9 Daemon Store"; }
    static StringSet uriSchemes() { return {"unix"}; }
    static std::string doc() { return "Nix worker protocol over native authenticated TLS connections."; }
    ref<Store> openStore() const override;
    StoreReference getReference() const override {
        return {.variant = StoreReference::Daemon{}, .params = getQueryParams()};
    }
};

struct Plan9DaemonStore : LocalFSStore, RemoteStore, Plan9RootStore
{
    using Config = Plan9DaemonConfig;
    ref<const Config> config;
    struct Connection : RemoteStore::Connection {
        Pid pid;
        Pipe input, output;
        ~Connection() {
            input.writeSide.close();
            output.readSide.close();
        }
        void closeWrite() override { input.writeSide.close(); }
    };
    explicit Plan9DaemonStore(ref<const Config> config)
        : Store(*config), LocalFSStore(*config), RemoteStore(*config), config(config) {}
    ref<RemoteStore::Connection> openConnection() override {
        if (config->keyPattern.get().find_first_of("\r\n!") != std::string::npos)
            throw Error("daemon key-pattern must contain public factotum attributes only");
        auto helper = ExecutablePath::load().findPath("nix-store-service");
        auto connection = make_ref<Connection>();
        connection->input.create();
        connection->output.create();
        connection->pid = startProcess([&] {
            if (n9_rfork(1 << 3 /* RFNOTEG */) == -1)
                throw SysError(cc9_errno_from_errstr_or(EIO), "creating daemon client note group");
            if (dup2(connection->input.readSide.get(), 0) == -1 ||
                dup2(connection->output.writeSide.get(), 1) == -1)
                throw SysError("connecting daemon pipes");
            restoreProcessContext();
            Strings args{helper.string(), "-c", "-p", std::to_string(clientProcess),
                "-a", config->address, "-k", config->keyPattern};
            execv(helper.c_str(), stringsToCharPtrs(args).data());
            throw SysError("starting daemon connection");
        });
        connection->input.readSide.close();
        connection->output.writeSide.close();
        connection->to.fd = connection->input.writeSide.get();
        connection->from.fd = connection->output.readSide.get();
        connection->startTime = std::chrono::steady_clock::now();
        return connection;
    }
    ref<SourceAccessor> getFSAccessor(bool requireValid = true) override {
        return LocalFSStore::getFSAccessor(requireValid);
    }
    std::shared_ptr<SourceAccessor> getFSAccessor(const StorePath & path, bool requireValid = true) override {
        return LocalFSStore::getFSAccessor(path, requireValid);
    }
    void narFromPath(const StorePath & path, Sink & sink) override {
        Store::narFromPath(path, sink);
    }
    void requireRoots(ConnectionHandle & connection) {
        if (!connection->protoVersion.features.contains(plan9RootsFeature))
            throw Error("the store service does not support shared roots and profiles; update it first");
    }
    std::filesystem::path addPermRoot(const StorePath & path, const std::filesystem::path & root) override {
        auto connection(getConnection());
        requireRoots(connection);
        connection->to << WorkerProto::Op::AddPermRoot;
        WorkerProto::write(*this, *connection, path);
        connection->to << root.string();
        connection.processStderr();
        return readString(connection->from);
    }
    std::string rootOperation(std::string_view action, const Strings & args) override {
        auto connection(getConnection());
        requireRoots(connection);
        connection->to << WorkerProto::Op::Plan9Roots << action << args;
        connection.processStderr();
        return readString(connection->from);
    }
};

ref<Store> Plan9DaemonConfig::openStore() const {
    return make_ref<Plan9DaemonStore>(ref{shared_from_this()});
}
static RegisterStoreImplementation<Plan9DaemonConfig> registerPlan9Daemon;

}
