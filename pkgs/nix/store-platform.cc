#include "nix/store/build-result.hh"
#include "nix/store/local-store.hh"
#include "nix/store/local-settings.hh"
#include "nix/util/signals.hh"

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

// A kernel service gate works even before the store's directories exist.
// Use the same canonical store path and service namespace for all clients.
static std::string storeService(const std::filesystem::path &dbDir)
{
    auto key = hashString(HashAlgorithm::SHA256, canonPath(dbDir).string());
    return "#s/nix9-store-" + key.to_string(HashFormat::Base16, false);
}

static PathLocks lockStoreAt(const std::filesystem::path &dbDir)
{
    return PathLocks({storeService(dbDir)});
}

PathLocks LocalStore::lockStore()
{
    return lockStoreAt(dbDir);
}

void LocalStore::markStoreUsed()
{
    // Called under the startup gate. Unlike locks, this service survives close
    // and process death, but not reboot. Never remove it during this boot.
    auto marker = storeService(dbDir) + "-used";
    if (pathExists(marker)) return;
    AutoCloseFD fd(n9_create(marker.c_str(), 1 | 32 | 0x1000, 0600));
    if (!fd) throw SysError(cc9_errno_from_errstr_or(EIO), "marking store use");
}

void recoverLocalStore(const LocalStoreConfig &config)
{
    auto dbDir = config.stateDir.get() / "db";
    auto gate = lockStoreAt(dbDir);
    if (pathExists(storeService(dbDir) + "-used"))
        throw Error("recovery requires a reboot before any client opens this store");
    if (config.readOnly || config.realStoreDir.get().string() != config.storeDir)
        throw Error("recovery requires a writable, non-diverted local store");
    if (readFile(dbDir / "schema") != std::to_string(nixSchemaVersion))
        throw Error("unsupported store schema for recovery");

    // All old clients died at reboot; the gate keeps new ones out. Preserve
    // the hot journal: SQLite must roll it back before we inspect ValidPaths.
    std::filesystem::remove(dbDir / "db.sqlite.p9lock");
    SQLite db(dbDir / "db.sqlite", {.mode = SQLiteOpenMode::NoCreate, .useWAL = false});
    StringSet valid;
    SQLiteStmt query(db, "SELECT path FROM ValidPaths");
    auto rows = query.use();
    while (rows.next()) valid.insert(rows.getStr(0));

    auto removeMarkers = [](const std::filesystem::path &dir) {
        for (auto &entry : DirectoryIterator{dir}) {
            checkInterrupt();
            if (!entry.is_regular_file())
                throw Error("unexpected recovery marker %s", PathFmt(entry.path()));
            std::filesystem::remove(entry.path());
        }
    };
    removeMarkers(dbDir / "clients");
    removeMarkers(config.stateDir.get() / "temproots");
    for (auto &entry : DirectoryIterator{config.realStoreDir.get()}) {
        checkInterrupt();
        auto name = entry.path().filename().string();
        if (name.starts_with("tmp-") && entry.is_directory()) {
            std::filesystem::remove(entry.path() / ".lock");
        } else if (name.ends_with(".lock") && entry.is_regular_file()
                   && !valid.contains(entry.path().string())) {
            // A registered output may itself end in .lock. Only remove an
            // empty, unregistered marker belonging to a syntactic store path.
            try {
                config.parseStorePath(entry.path().string().substr(0, entry.path().string().size() - 5));
            } catch (const BadStorePath &) { continue; }
            if (entry.file_size() == 0) std::filesystem::remove(entry.path());
        }
    }
    printInfo("store recovery complete");
}

void LocalStore::requireExclusiveStore()
{
    // Workers share the connection but have different native process IDs.
    auto own = fnTempRoots.filename().string() + ".lock";
    for (auto &entry : DirectoryIterator{dbDir / "clients"})
        if (entry.path().filename() != own)
            throw Error("exclusive store access required: another 9front client is active");
}

// Operations without native implementations fail explicitly.
[[noreturn]] static void unsupported(const char *operation)
{
    throw Error("%s is not supported on 9front", operation);
}

static AutoCloseFD ephemeralFile(const std::filesystem::path &path)
{
    // ORDWR | OCEXEC | ORCLOSE | OEXCL: never replace an existing live file.
    AutoCloseFD fd(n9_create(path.c_str(), 2 | 32 | 64 | 0x1000, 0600));
    if (!fd) throw SysError(cc9_errno_from_errstr_or(EIO), "creating %s", PathFmt(path));
    return fd;
}

void LocalStore::addTempRoot(const StorePath &path)
{
    // Collection requires exclusive client access. Also serialize this
    // connection's root updates with collection. Close/kill/exec removes roots.
    auto gcLock = _fdGCLock.lock();
    auto fd = _fdTempRoots.lock();
    if (!*fd) *fd = ephemeralFile(fnTempRoots);
    writeFull(fd->get(), printStorePath(path) + '\0');
}

std::pair<std::filesystem::path, AutoCloseFD> LocalStore::createTempDirInStore()
{
    auto gcLock = _fdGCLock.lock();
    auto path = createTempDir(config->realStoreDir.get(), "tmp", 0700);
    AutoDelete cleanup(path);
    auto fd = ephemeralFile(path / ".lock");
    cleanup.cancel();
    return {path, std::move(fd)};
}

std::filesystem::path IndirectRootStore::addPermRoot(
    const StorePath &path, const std::filesystem::path &root)
{
    auto &store = dynamic_cast<LocalStore &>(*this);
    auto rootsDir = canonPath(store.config->stateDir.get() / "gcroots");
    auto target = canonPath(root);
    if (!isInDir(target, rootsDir))
        throw Error("9front permanent roots must be files below %s", PathFmt(rootsDir));
    auto storeLock = lockStoreAt(store.dbDir);
    addTempRoot(path);
    if (!isValidPath(path))
        throw InvalidPath("cannot root invalid path '%s'", printStorePath(path));
    createDirs(target.parent_path());
    auto contents = printStorePath(path) + '\n';
    bool exists = pathExists(target);
    if (exists && readFile(target) == contents) return target;
    // The store gate excludes GC while create truncates and we write the root.
    // A failed write leaves no final newline, so later GC refuses to collect.
    AutoCloseFD fd(n9_create(target.c_str(), 1 | 32 | (exists ? 0 : 0x1000), 0600));
    if (!fd) throw SysError(cc9_errno_from_errstr_or(EIO), "writing root %s", PathFmt(target));
    writeFull(fd.get(), contents);
    return target;
}

void LocalStore::addIndirectRoot(const std::filesystem::path &)
{
    unsupported("indirect GC roots");
}

void LocalStore::findRoots(const std::filesystem::path &path,
                          std::filesystem::file_type type, Roots &roots)
{
    if (type == std::filesystem::file_type::directory) {
        for (auto &entry : DirectoryIterator{path}) {
            checkInterrupt();
            findRoots(entry.path(), entry.symlink_status().type(), roots);
        }
    } else if (type == std::filesystem::file_type::regular) {
        auto contents = readFile(path);
        if (contents.empty() || contents.back() != '\n')
            throw Error("malformed GC root %s", PathFmt(path));
        contents.pop_back();
        auto storePath = parseStorePath(contents);
        if (isValidPath(storePath)) roots[storePath].insert(path.string());
    } else {
        throw Error("unsupported GC root %s", PathFmt(path));
    }
}

void LocalStore::findRootsNoTemp(Roots &roots, bool censor)
{
    if (config->useRootsDaemon) unsupported("GC roots daemon");
    // Running programs need an explicit root; /proc discovery is not ported.
    findRoots(config->stateDir.get() / "gcroots", std::filesystem::file_type::directory, roots);
    if (censor)
        for (auto &[path, names] : roots) names = {"{censored}"};
}

void LocalStore::findTempRoots(Roots &roots, bool censor)
{
    auto fd = _fdTempRoots.lock();
    // Other clients may append roots, so exclude new clients and require
    // exclusive access before reading. Retain leftovers after power loss.
    for (auto &entry : DirectoryIterator{tempRootsDir}) {
        auto contents = readFile(entry.path());
        size_t pos = 0;
        while (pos < contents.size()) {
            auto end = contents.find('\0', pos);
            if (end == std::string::npos)
                throw Error("malformed temporary roots file %s", PathFmt(entry.path()));
            roots[parseStorePath(contents.substr(pos, end - pos))].insert(
                censor ? "{censored}" : "{temp:" + entry.path().filename().string() + "}");
            pos = end + 1;
        }
    }
}

Roots LocalStore::findRoots(bool censor)
{
    auto storeLock = lockStore();
    requireExclusiveStore();
    auto gcLock = _fdGCLock.lock();
    Roots roots;
    findRootsNoTemp(roots, censor);
    findTempRoots(roots, censor);
    return roots;
}

void LocalStore::autoGC(bool)
{
    if (config->getLocalSettings().getGCSettings().minFree != 0U)
        unsupported("automatic garbage collection");
}

void LocalStore::optimiseStore()
{
    unsupported("store optimisation");
}

void LocalStore::optimisePath(const std::filesystem::path &, RepairFlag)
{
    if (config->getLocalSettings().autoOptimiseStore)
        unsupported("store optimisation");
}

} // namespace nix
