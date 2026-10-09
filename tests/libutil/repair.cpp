#include "nix/store/globals.hh"
#include "nix/store/store-open.hh"
#include "nix/util/file-system.hh"
#include "nix/util/serialise.hh"
#include "nix/util/strings.hh"
#include <sys/stat.h>
#include <unistd.h>

static std::string replacement;

extern "C" long __real_n9_pwrite(int, const void *, long, long long);

// Only the probe wraps writes. Pause in the real repair copy after a short
// write, so the VM test can persist a partial replacement and cut power.
extern "C" long __wrap_n9_pwrite(int fd, const void *data, long size, long long offset) {
    struct stat file, target;
    if (!replacement.empty() && size && fstat(fd, &file) == 0 &&
        stat(replacement.c_str(), &target) == 0 &&
        file.st_dev == target.st_dev && file.st_ino == target.st_ino) {
        replacement.clear();
        auto written = __real_n9_pwrite(fd, data, 1, offset);
        if (written != 1) throw std::runtime_error("repair short write failed");
        nix::writeFile("/tmp/nix9-repair-ready", "ready");
        for (;;) sleep(1);
    }
    return __real_n9_pwrite(fd, data, size, offset);
}

void interruptRepair(const char *package) {
    using namespace nix;
    initLibStore();
    settings.trustedPublicKeys = Strings{trim(readFile("/tmp/cache.pub"))};
    auto store = openStore();
    auto cache = openStore("file:///tmp/cache?store=/usr/local/nix/store");
    auto path = store->parseStorePath(package);
    auto info = cache->queryPathInfo(path);
    StringSink nar;
    cache->narFromPath(path, nar);
    StringSource source(nar.s);
    replacement = std::string(package) + "/bin/lua";
    store->addToStore(*info, source, Repair, CheckSigs);
    throw std::runtime_error("repair completed without the interruption point");
}
