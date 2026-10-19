#include "nix/fetchers/tarball.hh"
#include "nix/store/store-api.hh"
#include "nix/util/memory-source-accessor.hh"
#include "nix/util/tarfile.hh"

namespace nix::fetchers {

struct ArchiveSink : ExtendedFileSystemObjectSink
{
    MemorySink sink;

    explicit ArchiveSink(MemorySourceAccessor &tree) : sink(tree) {}

    void createDirectory(const CanonPath &path) override { sink.createDirectory(path); }

    void createRegularFile(const CanonPath &path, fun<void(CreateRegularFileSink &)> contents) override
    {
        if (sink.dst.pathExists(path))
            throw Error("duplicate archive member '%s'", path);
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

ref<SourceAccessor> downloadTarball(Store &store, const Settings &settings, const std::string &url)
{
    auto file = downloadFile(store, settings, parseURL(url), "source");
    auto data = store.requireStoreObjectAccessor(file.storePath)->readFile(CanonPath::root);
    StringSource source{data};
    TarArchive archive{source};
    auto tree = make_ref<MemorySourceAccessor>();
    ArchiveSink sink{*tree};
    sink.createDirectory(CanonPath::root);
    unpackTarfileToSink(archive, sink);
    archive.close();

    // Strip one enclosing directory, as the upstream tarball fetcher does.
    using Directory = MemorySourceAccessor::File::Directory;
    auto &entries = std::get<Directory>(tree->root->raw).entries;
    if (entries.size() == 1 && std::holds_alternative<Directory>(entries.begin()->second.raw)) {
        auto root = std::move(entries.begin()->second);
        tree->root = std::move(root);
    }
    return tree;
}

} // namespace nix::fetchers
