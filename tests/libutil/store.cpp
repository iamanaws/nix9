#include "nix/store/local-store.hh"
#include "nix/store/globals.hh"
#include "nix/util/archive.hh"
#include "nix/util/processes.hh"
#include <iostream>

void checkImports();

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

void checkStore() {
    using namespace nix;
    initLibStore(false);
    deletePath(root);
    StorePathSet expected;
    std::filesystem::path rootsFile, rootsDir;
    {
        auto store = openStore();
        require(store->queryAllValidPaths().empty(), "new store is not empty");
        rejected([] { openStore(); }, "second client bypassed store lock");

        auto dependency = file(*store, "dependency");
        auto dependent = file(*store, "dependent", {dependency.path});
        rootsFile = store->fnTempRoots;
        rootsDir = store->tempRootsDir;
        store->addTempRoot(dependency.path);
        store->addTempRoot(dependent.path);
        require(readFile(rootsFile) == store->printStorePath(dependency.path) + '\0' +
                store->printStorePath(dependent.path) + '\0', "temporary roots changed");
        expected = {dependency.path, dependent.path};
        // An earlier negative lookup must not survive registration.
        require(!store->isValidPath(dependent.path), "unregistered path is valid");
        store->registerValidPaths({{dependent.path, dependent}, {dependency.path, dependency}});
        require(store->queryAllValidPaths() == expected, "registration lost paths");
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
        rejected([&] { store->addIndirectRoot("/tmp/nix9-root"); }, "permanent roots reported success");
        GCResults results;
        rejected([&] { store->collectGarbage(GCOptions{}, results); }, "GC reported success");
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
        }
        _exit(0);
    });
    ready.writeSide.close(); finish.readSide.close();
    char byte;
    readFull(ready.readSide.get(), &byte, 1);
    rejected([] { openStore(); }, "competing process bypassed store lock");
    require(!statusOk(child.kill()), "killed store client reported success");
    require(std::filesystem::is_empty(rootsDir), "killed store client left temporary roots");
    {
        auto store = openStore();
        auto paths = store->queryAllValidPaths();
        auto survived = file(*store, "survives-kill");
        expected.insert(survived.path);
        require(paths == expected,
                "committed registration lost after killing client");
    }
    deletePath(root);
    checkImports();
    std::cout << "libstore LocalStore PASS\n";
}
