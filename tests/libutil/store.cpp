#include "nix/store/local-store.hh"
#include "nix/store/globals.hh"
#include "nix/util/archive.hh"
#include "nix/util/processes.hh"
#include "nix/util/signature/local-keys.hh"
#include <iostream>

void checkImports();
void checkStoreClients();

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

template<class F> static void rejected(F action, const char *what) {
    bool failed = false;
    try { action(); }
    catch (const nix::Error &) { failed = true; }
    require(failed, what);
}

static const char *root = "/tmp/nix9-local-store";

static nix::ref<nix::LocalStore> openStore() {
    return nix::make_ref<nix::LocalStore>(
        nix::make_ref<nix::LocalStore::Config>(root, nix::Store::Config::Params{}));
}

// Exercise the general cache fixes in an isolated connection. Native stores
// normally disable this cache because other clients can update the database.
struct CachedStore : nix::LocalStore {
    CachedStore(nix::ref<const LocalStore::Config> config)
        : Store(*config), LocalFSStore(*config), LocalStore(config) {
        pathInfoCache = nix::make_ref<decltype(pathInfoCache)::element_type>(32);
    }
};

static nix::ValidPathInfo file(nix::LocalStore &store, const std::string &name,
                              const nix::StorePathSet &references = {}) {
    using namespace nix;
    StringSink nar;
    dumpString(name, nar);
    auto hash = hashString(HashAlgorithm::SHA256, nar.s);
    auto info = ValidPathInfo::makeFromCA(store, name, FixedOutputInfo{
        .method=FileIngestionMethod::NixArchive, .hash=hash,
        .references={.others=references}}, hash);
    info.narSize = nar.s.size();
    info.registrationTime = 1234567890;
    writeFile(store.config->realStoreDir.get() / info.path.to_string(), name);
    return info;
}

static void checkVerification() {
    using namespace nix;
    {
        auto store = openStore();
        auto dependency = file(*store, "verify-dependency");
        auto dependent = file(*store, "verify-dependent", {dependency.path});
        store->registerValidPaths({{dependency.path, dependency}, {dependent.path, dependent}});
        require(!store->verifyStore(true, NoRepair), "healthy store failed verification");
        deletePath(store->toRealPath(dependency.path));
        require(store->verifyStore(true, NoRepair), "verification missed a referenced missing path");
        require(store->isValidPath(dependency.path) && store->isValidPath(dependent.path),
                "verification removed referenced registrations");
        require(readFile(store->toRealPath(dependent.path)) == "verify-dependent",
                "verification changed a dependent path");
        auto unknown = store->config->realStoreDir.get() / "unfinished";
        writeFile(unknown, "keep");
        deletePath(store->toRealPath(dependent.path));
        require(!store->verifyStore(true, NoRepair), "verification failed to reconcile missing paths");
        require(store->queryAllValidPaths().empty(), "missing unreferenced paths remained registered");
        require(readFile(unknown) == "keep", "verification deleted an unknown file");
    }
    deletePath(root);
}

static void checkGC() {
    using namespace nix;
    StorePathSet kept;
    std::filesystem::path permanent;
    {
        auto store = openStore();
        auto dependency = file(*store, "gc-dependency");
        auto package = file(*store, "gc-package", {dependency.path});
        auto dead = file(*store, "gc-unused");
        auto deadUser = file(*store, "gc-unused-user", {dead.path});
        store->registerValidPaths({{dependency.path, dependency}, {package.path, package},
                                  {dead.path, dead}, {deadUser.path, deadUser}});
        kept = {dependency.path, package.path};
        permanent = store->config->stateDir.get() / "gcroots" / "package";
        store->addPermRoot(package.path, permanent);
        store->addPermRoot(package.path, permanent); // Idempotent.
        store->addPermRoot(dead.path, permanent);
        require(readFile(permanent) == store->printStorePath(dead.path) + '\n', "root was not replaced");
        std::filesystem::permissions(permanent, std::filesystem::perms::owner_read);
        store->addPermRoot(dead.path, permanent); // An unchanged root needs no write.
        rejected([&] { store->addPermRoot(package.path, permanent); }, "read-only root was replaced");
        require(readFile(permanent) == store->printStorePath(dead.path) + '\n', "failed update changed root");
        std::filesystem::permissions(permanent, std::filesystem::perms::owner_read | std::filesystem::perms::owner_write);
        store->addPermRoot(package.path, permanent);
        rejected([&] { store->addPermRoot(StorePath(std::string(32, '0') + "-missing"), permanent); },
                 "invalid path replaced a root");
        rejected([&] { store->addPermRoot(package.path, "/tmp/outside-root"); }, "outside root accepted");
        require(readFile(permanent) == store->printStorePath(package.path) + '\n', "root contents changed");
    }
    {
        auto store = openStore();
        require(store->findRoots(false).size() == 1, "permanent root did not survive reopening");
        auto temporary = file(*store, "gc-temporary");
        store->registerValidPath(temporary);
        store->addTempRoot(temporary.path);
        auto directory = createTempDir(store->config->realStoreDir.get(), "tmp", 0700);
        writeFile(directory / ".lock", "");
        writeFile(directory / "work", "active import");
        auto unknown = store->config->realStoreDir.get() / "unfinished";
        writeFile(unknown, "incomplete import");
        GCOptions options;
        options.action = GCOptions::gcReturnLive;
        GCResults live;
        store->collectGarbage(options, live);
        require(live.paths.size() == 3, "GC live closure omitted a permanent or temporary root");
        for (auto &path : kept)
            require(live.paths.count(store->printStorePath(path)), "GC lost rooted dependency");
        options.action = GCOptions::gcReturnDead;
        GCResults dead;
        store->collectGarbage(options, dead);
        require(dead.paths.size() == 2, "GC dead closure changed");
        require(pathExists(unknown) && pathExists(directory / "work"), "GC query deleted files");

        options.action = GCOptions::gcDeleteSpecific;
        options.pathsToDelete = kept;
        GCResults results;
        rejected([&] { store->collectGarbage(options, results); }, "GC deleted rooted path");
        options = GCOptions{};
        auto rootContents = readFile(permanent);
        rootContents.pop_back();
        auto rooted = store->parseStorePath(rootContents);
        for (auto contents : {std::string{}, store->printStorePath(temporary.path)}) {
            writeFile(permanent, contents); // Truncation or a write without the final newline.
            rejected([&] { store->collectGarbage(options, results); }, "GC ignored interrupted root update");
            require(store->queryAllValidPaths().size() == 5, "interrupted root update allowed deletion");
            store->addPermRoot(rooted, permanent);
        }
        auto malformed = permanent.parent_path() / "broken";
        writeFile(malformed, "incomplete");
        rejected([&] { store->collectGarbage(options, results); }, "GC ignored malformed root");
        require(store->queryAllValidPaths().size() == 5, "failed GC deleted valid paths");
        deletePath(malformed);
        store->collectGarbage(options, results);
        auto expected = kept;
        expected.insert(temporary.path);
        require(store->queryAllValidPaths() == expected, "GC kept garbage or lost live paths");
        require(pathExists(directory / "work") && !pathExists(unknown), "GC mishandled temporary directories");
        for (auto &path : dead.paths)
            require(!pathExists(store->toRealPath(store->parseStorePath(path))), "GC left deleted contents");
        deletePath(directory / ".lock");
        store->collectGarbage(options, results);
        require(!pathExists(directory), "GC kept released temporary directory");
    }
    {
        auto store = openStore();
        GCResults results;
        store->collectGarbage(GCOptions{}, results);
        require(store->queryAllValidPaths() == kept, "temporary root survived client close");
        deletePath(permanent);
        store->collectGarbage(GCOptions{}, results);
        require(store->queryAllValidPaths().empty(), "removed root still retained closure");
    }
    deletePath(root);
}

void checkStore() {
    using namespace nix;
    initLibStore(false);
    deletePath(root);
    StorePathSet expected;
    std::filesystem::path rootsFile, rootsDir, clientsDir;
    {
        auto store = make_ref<CachedStore>(make_ref<LocalStore::Config>(root, Store::Config::Params{}));
        require(store->queryAllValidPaths().empty(), "new store is not empty");
        rejected([] { openStore(); }, "duplicate connection in one process was accepted");

        auto dependency = file(*store, "dependency");
        dependency.registrationTime = 0;
        auto dependent = file(*store, "dependent", {dependency.path});
        rootsFile = store->fnTempRoots;
        rootsDir = store->tempRootsDir;
        clientsDir = store->dbDir / "clients";
        store->addTempRoot(dependency.path);
        store->addTempRoot(dependent.path);
        require(readFile(rootsFile) == store->printStorePath(dependency.path) + '\0' +
                store->printStorePath(dependent.path) + '\0', "temporary roots changed");
        expected = {dependency.path, dependent.path};
        // An earlier negative lookup must not survive registration.
        require(!store->isValidPath(dependent.path), "unregistered path is valid");
        store->registerValidPaths({{dependent.path, dependent}, {dependency.path, dependency}});
        require(store->queryAllValidPaths() == expected, "registration lost paths");
        require(store->queryPathInfo(dependency.path)->registrationTime != 0,
                "cache omitted the database registration time");
        auto info = store->queryPathInfo(dependent.path);
        require(info->narHash == dependent.narHash && info->narSize == dependent.narSize &&
                info->registrationTime == dependent.registrationTime && info->ca == dependent.ca &&
                info->references == dependent.references, "registered metadata changed");
        require(info->isContentAddressed(*store), "content address no longer matches");
        require(store->queryPathFromHashPart(std::string(dependent.path.hashPart())) == dependent.path,
                "hash lookup failed");
        StorePathSet referrers, closure;
        store->queryReferrers(dependency.path, referrers);
        require(referrers == StorePathSet{dependent.path}, "referrer lookup failed");
        store->computeFSClosure(dependent.path, closure);
        require(closure == expected, "dependency closure changed");

        dependent.ultimate = true;
        store->registerValidPath(dependent);
        require(store->queryPathInfo(dependent.path)->ultimate, "updated metadata stayed cached");
        auto signature = SecretKey::generate("store-test").signDetached("test");
        store->addSignatures(dependent.path, {signature});
        require(store->queryPathInfo(dependent.path)->sigs.contains(signature),
                "added signature stayed hidden by cached metadata");

        // Failed batches must disappear from both the database and the path cache.
        auto missing = file(*store, "missing");
        auto bad = file(*store, "bad-reference", {missing.path});
        rejected([&] { store->registerValidPath(bad); }, "missing reference accepted");
        require(!store->isValidPath(bad.path) && store->queryAllValidPaths() == expected,
                "failed registration left a valid path");
        auto a = file(*store, "cycle-a"), b = file(*store, "cycle-b");
        a.ca.reset(); b.ca.reset();
        a.references = {b.path}; b.references = {a.path};
        rejected([&] { store->registerValidPaths({{a.path, a}, {b.path, b}}); }, "reference cycle accepted");
        require(!store->isValidPath(a.path) && !store->isValidPath(b.path) &&
                store->queryAllValidPaths() == expected, "cycle rollback left valid paths");
        auto mismatch = file(*store, "wrong-content-address");
        mismatch.ca->hash = hashString(HashAlgorithm::SHA256, "different");
        rejected([&] { store->registerValidPath(mismatch); }, "incorrect content address accepted");

        store->buildPaths({});
        rejected([&] { store->addIndirectRoot("/tmp/nix9-root"); }, "indirect roots reported success");
    }
    require(!std::filesystem::exists(rootsFile), "closing store left temporary roots");
    {
        auto store = openStore();
        require(store->queryAllValidPaths() == expected, "reopening lost registrations");
        auto dependent = file(*store, "dependent", {file(*store, "dependency").path});
        require(store->queryPathInfo(dependent.path)->ultimate, "metadata update was not persisted");
    }

    Pipe ready, finish;
    ready.create(); finish.create();
    Pid child = startProcess([&] {
        ready.readSide.close(); finish.writeSide.close();
        {
            auto store = openStore();
            auto info = file(*store, "survives-kill");
            store->addTempRoot(info.path);
            store->registerValidPath(info);
            writeFull(ready.writeSide.get(), "r");
            char byte;
            readFull(finish.readSide.get(), &byte, 1);
            info.ultimate = true;
            store->registerValidPath(info);
            auto later = file(*store, "after-peer-open");
            store->registerValidPath(later);
            writeFull(ready.writeSide.get(), "u");
            readFull(finish.readSide.get(), &byte, 1);
        }
        _exit(0);
    });
    ready.writeSide.close(); finish.readSide.close();
    char byte;
    readFull(ready.readSide.get(), &byte, 1);
    {
        auto store = openStore();
        auto survived = file(*store, "survives-kill");
        auto later = file(*store, "after-peer-open");
        require(!store->queryPathInfo(survived.path)->ultimate, "child metadata changed early");
        rejected([&] { store->queryPathInfo(later.path); }, "unregistered peer path was valid");
        writeFull(finish.writeSide.get(), "u");
        readFull(ready.readSide.get(), &byte, 1);
        require(store->queryPathInfo(survived.path)->ultimate, "peer metadata remained cached");
        require(store->isValidPath(later.path), "peer registration remained negatively cached");
        GCResults result;
        rejected([&] { store->collectGarbage(GCOptions{}, result); }, "GC ran alongside a live client");
        rejected([&] { store->verifyStore(true, NoRepair); }, "verification ran alongside a live client");
        require(pathExists(store->toRealPath(survived.path)), "GC deleted a live client's input");
        StringSink nar;
        dumpString("survives-kill", nar);
        StringSource repairSource(nar.s);
        rejected([&] { store->addToStore(survived, repairSource, Repair, NoCheckSigs); },
                 "repair ran alongside a live client");
        require(readFile(store->toRealPath(survived.path)) == "survives-kill",
                "rejected repair changed a live client's input");
        expected.insert(later.path);
    }
    require(!statusOk(child.kill()), "killed store client reported success");
    require(std::filesystem::is_empty(rootsDir), "killed store client left temporary roots");
    require(std::filesystem::is_empty(clientsDir), "killed store client left membership files");
    {
        auto store = openStore();
        auto paths = store->queryAllValidPaths();
        auto survived = file(*store, "survives-kill");
        expected.insert(survived.path);
        require(paths == expected,
                "committed registration lost after killing client");
    }
    deletePath(root);
    checkGC();
    checkVerification();
    checkImports();
    checkStoreClients();
    std::cout << "libstore LocalStore PASS\n";
}
