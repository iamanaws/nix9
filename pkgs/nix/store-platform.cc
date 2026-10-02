#include "nix/store/build-result.hh"
#include "nix/store/local-store.hh"
#include "nix/store/local-settings.hh"

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

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
    // The store's lifetime lock excludes other clients; GC is disabled. Keep
    // upstream's NUL-separated records, with native close/kill/exec cleanup.
    auto fd = _fdTempRoots.lock();
    if (!*fd) *fd = ephemeralFile(fnTempRoots);
    writeFull(fd->get(), printStorePath(path) + '\0');
}

std::pair<std::filesystem::path, AutoCloseFD> LocalStore::createTempDirInStore()
{
    auto path = createTempDir(config->realStoreDir.get(), "tmp", 0700);
    AutoDelete cleanup(path);
    auto fd = ephemeralFile(path / ".lock");
    cleanup.cancel();
    return {path, std::move(fd)};
}

void LocalStore::addIndirectRoot(const std::filesystem::path &)
{
    unsupported("GC roots");
}

Roots LocalStore::findRoots(bool)
{
    unsupported("GC roots");
}

void LocalStore::collectGarbage(const GCOptions &, GCResults &)
{
    unsupported("garbage collection");
}

void LocalStore::autoGC(bool)
{
    if (config->getLocalSettings().getGCSettings().minFree != 0)
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
