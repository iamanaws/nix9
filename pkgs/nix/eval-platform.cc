#include "nix/fetchers/tarball.hh"
#include "nix/store/store-api.hh"
#include "nix/util/fs-sink.hh"
#include "nix/util/posix-source-accessor.hh"
#include "nix/util/tarfile.hh"

namespace nix::fetchers {

struct ArchiveSink : ExtendedFileSystemObjectSink
{
    RestoreSink sink{false};

    explicit ArchiveSink(const std::filesystem::path &root)
    {
        sink.dstPath = root;
        sink.createDirectory(CanonPath::root);
    }

    void createDirectory(const CanonPath &path) override { createDirs(sink.dstPath / path.rel()); }

    void createRegularFile(const CanonPath &path, fun<void(CreateRegularFileSink &)> contents) override
    {
        if (pathExists(sink.dstPath / path.rel()))
            throw Error("duplicate archive member '%s'", path);
        if (auto parent = path.parent())
            createDirectory(*parent);
        sink.createRegularFile(path, contents);
    }

    void createSymlink(const CanonPath &, const std::string &) override
    {
        throw Error("archive symbolic links are not supported on Plan 9");
    }

    void createHardlink(const CanonPath &, const CanonPath &) override
    {
        throw Error("archive hard links are not supported on Plan 9");
    }
};

struct TarballAccessor : PosixSourceAccessor
{
    AutoDelete cleanup;

    TarballAccessor(std::filesystem::path root, AutoDelete cleanup)
        : PosixSourceAccessor(std::move(root)), cleanup(std::move(cleanup)) {}
};

ref<SourceAccessor> downloadTarball(Store &store, const Settings &settings, const std::string &url)
{
    auto file = downloadFile(store, settings, parseURL(url), "source");
    auto accessor = store.requireStoreObjectAccessor(file.storePath);
    auto source = sinkToSource([&](Sink &sink) { accessor->readFile(CanonPath::root, sink); });
    TarArchive archive{*source};
    AutoDelete temp{createTempDir("", "nix-tarball", 0700)};
    auto root = temp.path() / "contents";
    ArchiveSink sink{root};
    unpackTarfileToSink(archive, sink);
    archive.close();

    // Strip one enclosing directory, as the upstream tarball fetcher does.
    auto tree = makeFSSourceAccessor(root);
    auto entries = tree->readDirectory(CanonPath::root);
    if (entries.size() == 1 && tree->lstat(CanonPath{entries.begin()->first}).type == SourceAccessor::tDirectory)
        root /= entries.begin()->first;
    return make_ref<TarballAccessor>(std::move(root), std::move(temp));
}

} // namespace nix::fetchers
