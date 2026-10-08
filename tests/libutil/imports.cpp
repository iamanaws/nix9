#include "nix/store/local-store.hh"
#include "nix/store/globals.hh"
#include "nix/util/archive.hh"
#include <future>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

template<class F> static void rejected(F action, const char *what) {
    bool failed = false;
    try { action(); }
    catch (const nix::Error &) { failed = true; }
    require(failed, what);
}

static nix::ValidPathInfo metadata(const nix::LocalStore &store, const std::string &name,
                                   const std::string &nar, const nix::StorePathSet &refs = {}) {
    using namespace nix;
    auto hash = hashString(HashAlgorithm::SHA256, nar);
    auto info = ValidPathInfo::makeFromCA(store, name, FixedOutputInfo{
        .method=FileIngestionMethod::NixArchive, .hash=hash, .references={.others=refs}}, hash);
    info.narSize = nar.size();
    return info;
}

void checkImports() {
    using namespace nix;
    const auto root = "/tmp/nix9-import-store";
    deletePath(root);
    auto config = make_ref<LocalStore::Config>(root, Store::Config::Params{});
    auto nar = readFile("/tmp/import.nar"); // Created by host Nix.
    StorePathSet expected;
    {
        auto store = make_ref<LocalStore>(config);
        auto info = metadata(*store, "import-tree", nar);
        auto path = store->toRealPath(info.path);
        settings.getLocalSettings().fsyncStorePaths = true;
        StringSource input(nar);
        store->addToStore(info, input, NoRepair, CheckSigs);
        require(store->isValidPath(info.path), "import was not registered");
        require(store->queryPathInfo(info.path)->narHash == info.narHash &&
                store->queryPathInfo(info.path)->narSize == nar.size(), "import metadata changed");
        StringSink output;
        store->narFromPath(info.path, output);
        require(output.s == nar, "imported NAR differs from host Nix");
        for (auto name : {"", "/binary", "/executable", "/empty"}) {
            auto st = lstat(path.string() + name);
            auto mode = std::string_view(name) == "/binary" ? 0444 : 0555;
            require((st.st_mode & 0777) == mode && st.st_mtime == 1,
                    "import permissions or timestamp changed");
        }
        expected.insert(info.path);

        // Re-importing a valid path must leave it intact and consume the NAR.
        StringSource duplicate(nar);
        store->addToStore(info, duplicate, NoRepair, CheckSigs);
        require(duplicate.drain().empty(), "duplicate import left unread bytes");
        for (auto failure : {"hash", "size", "truncated", "ca"}) {
            auto bad = info;
            auto bytes = nar;
            if (std::string_view(failure) == "hash") bad.narHash = hashString(HashAlgorithm::SHA256, "wrong");
            if (std::string_view(failure) == "size") ++bad.narSize;
            if (std::string_view(failure) == "truncated") bytes.pop_back();
            if (std::string_view(failure) == "ca") bad.ca->hash = hashString(HashAlgorithm::SHA256, "wrong");
            StringSource input(bytes);
            rejected([&] { store->addToStore(bad, input, Repair, NoCheckSigs); }, "invalid repair accepted");
            StringSink unchanged;
            store->narFromPath(info.path, unchanged);
            require(unchanged.s == nar, "rejected repair changed stored data");
        }
        std::filesystem::permissions(path, std::filesystem::perms::owner_write,
                                     std::filesystem::perm_options::add);
        deletePath(path / "binary");
        StringSource repair(nar);
        // Substitution repairs through a worker using the same store connection.
        std::async(std::launch::async, [&] {
            store->addToStore(info, repair, Repair, CheckSigs);
        }).get();
        StringSink repaired;
        store->narFromPath(info.path, repaired);
        require(repaired.s == nar, "repair did not restore the original NAR");

        // Exercise both the in-memory and temporary-directory ingestion paths.
        for (size_t limit : {size_t{1 << 20}, size_t{8}}) {
            settings.getLocalSettings().narBufferSize = limit;
            StringSource stream(nar);
            auto imported = store->addToStoreFromDump(stream, "stream-" + std::to_string(limit),
                FileSerialisationMethod::NixArchive, ContentAddressMethod::Raw::NixArchive,
                HashAlgorithm::SHA256, {info.path}, NoRepair);
            require(store->queryPathInfo(imported)->references == StorePathSet{info.path},
                    "stream import lost references");
            StringSink roundtrip;
            store->narFromPath(imported, roundtrip);
            require(roundtrip.s == nar, "stream import changed contents");
            expected.insert(imported);
        }
        for (auto &entry : std::filesystem::directory_iterator(config->realStoreDir.get()))
            require(!entry.path().filename().string().starts_with("tmp-") &&
                    !entry.path().filename().string().starts_with("repair-"), "temporary import directory leaked");

        for (auto failure : {"hash", "size", "truncated", "reference", "link", "gc", "optimise"}) {
            auto bytes = nar;
            if (std::string_view(failure) == "link") {
                StringSink link;
                link << narVersionMagic1 << "(" << "type" << "symlink" << "target" << "/missing" << ")";
                bytes = link.s;
            }
            auto bad = metadata(*store, "bad-" + std::string(failure), bytes);
            if (std::string_view(failure) == "hash") bad.narHash = hashString(HashAlgorithm::SHA256, "wrong");
            if (std::string_view(failure) == "size") ++bad.narSize;
            if (std::string_view(failure) == "truncated") bytes.pop_back();
            if (std::string_view(failure) == "reference") {
                auto missing = metadata(*store, "missing", nar);
                bad = metadata(*store, "bad-reference", nar, {missing.path});
            }
            settings.getLocalSettings().minFree = std::string_view(failure) == "gc" ? 1 : 0;
            settings.getLocalSettings().autoOptimiseStore = std::string_view(failure) == "optimise";
            StringSource stream(bytes);
            rejected([&] { store->addToStore(bad, stream, NoRepair, CheckSigs); }, "invalid import accepted");
            settings.getLocalSettings().minFree = 0;
            settings.getLocalSettings().autoOptimiseStore = false;
            auto failedPath = store->toRealPath(bad.path);
            require(!store->isValidPath(bad.path) && !std::filesystem::exists(failedPath) &&
                    !std::filesystem::exists(failedPath.string() + ".lock"), "failed import left state behind");
        }
        require(store->queryAllValidPaths() == expected, "failed imports changed registrations");
    }
    {
        auto store = make_ref<LocalStore>(config);
        require(store->queryAllValidPaths() == expected, "reopening lost imported paths");
        for (auto &path : expected) {
            StringSink roundtrip;
            store->narFromPath(path, roundtrip);
            require(roundtrip.s == nar, "reopening changed imported contents");
        }
    }
    deletePath(root);
}
