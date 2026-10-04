#include "nix/store/local-store.hh"
#include "nix/util/processes.hh"
#include "nix/util/serialise.hh"

static void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void checkStoreClients()
{
    using namespace nix;
    const char *root = "/tmp/nix9-client-store";
    deletePath(root);
    Pipe ready, start;
    ready.create(); start.create();
    Pid children[2];
    constexpr int imports = 20;
    for (int client = 0; client < 2; ++client) {
        children[client] = startProcess([&] {
            ready.readSide.close(); start.writeSide.close();
            {
                auto store = make_ref<LocalStore>(make_ref<LocalStore::Config>(root, Store::Config::Params{}));
                writeFull(ready.writeSide.get(), "r");
                char byte;
                readFull(start.readSide.get(), &byte, 1);
                for (int i = 0; i < imports; ++i) {
                    std::string name = "client-" + std::to_string(client) + "-" + std::to_string(i);
                    StringSource source(name);
                    auto path = store->addToStoreFromDump(source, name,
                        FileSerialisationMethod::Flat, ContentAddressMethod::Raw::Flat,
                        HashAlgorithm::SHA256, {}, NoRepair);
                    require(store->isValidPath(path), "concurrent import was not registered");
                }
            }
            _exit(0);
        });
    }
    ready.writeSide.close(); start.readSide.close();
    char bytes[2];
    readFull(ready.readSide.get(), bytes, 2); // Both clients must open before either exits.
    writeFull(start.writeSide.get(), "rr");
    for (auto &child : children)
        require(statusOk(child.wait()), "concurrent store client failed");
    std::filesystem::path clients;
    {
        auto store = make_ref<LocalStore>(make_ref<LocalStore::Config>(root, Store::Config::Params{}));
        clients = store->dbDir / "clients";
        auto paths = store->queryAllValidPaths();
        require(paths.size() == 2 * imports, "concurrent imports lost registrations");
        for (auto &path : paths)
            require(readFile(store->toRealPath(path)) == path.name(), "concurrent import changed contents");
        GCResults collected;
        store->collectGarbage(GCOptions{}, collected);
        require(store->queryAllValidPaths().empty(), "closed clients prevented collection");
    }
    require(std::filesystem::is_empty(clients),
            "closed clients left membership files");
    deletePath(root);
}
