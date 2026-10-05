#include "nix/util/file-system.hh"
#include "nix/util/processes.hh"
#include <fcntl.h>
#include <sys/stat.h>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

void checkFileCopies() {
    using namespace nix;
    const std::filesystem::path root = "/tmp/nix9-copy";
    createDirs(root);
    AutoCloseFD directory(::open(root.c_str(), O_RDONLY));
    require(directory.get() >= 0, "cannot open copy test directory");
    auto source = root / "source", copy = root / "copy";
    for (mode_t mode : {0751, 0700, 0640}) {
        const std::string contents = "#!/bin/rc\necho copied-" + std::to_string(mode) + "\n";
        {
            AutoCloseFD fd(::open(source.c_str(), O_WRONLY | O_CREAT | O_EXCL, mode));
            require(fd.get() >= 0, "cannot create source");
            writeFull(fd.get(), contents);
        }
        require((lstat(source).st_mode & 0777) == mode, "open lost creation permissions");
        {
            AutoCloseFD fd(::openat(directory.get(), "copy", O_WRONLY | O_CREAT | O_EXCL, mode));
            require(fd.get() >= 0, "cannot create file with openat");
        }
        require((lstat(copy).st_mode & 0777) == mode, "openat lost creation permissions");
        require(::unlink(copy.c_str()) == 0, "cannot remove openat fixture");
        require(std::filesystem::copy_file(source, copy), "copy_file failed");
        require((lstat(copy).st_mode & 0777) == mode && readFile(copy) == contents,
                "new copy lost permissions or contents");
        if (mode & 0100)
            require(runProgram(copy.string(), false) == "copied-" + std::to_string(mode) + "\n",
                    "copied program did not execute");
        chmod(copy, 0600);
        writeFile(copy, "old contents");
        require(std::filesystem::copy_file(source, copy, std::filesystem::copy_options::overwrite_existing),
                "overwrite failed");
        require((lstat(copy).st_mode & 0777) == mode && readFile(copy) == contents,
                "overwrite lost permissions or contents");
        // Opening an existing file must preserve its permissions, even with O_CREAT.
        {
            AutoCloseFD fd(::open(copy.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600));
            require(fd.get() >= 0, "cannot truncate existing file");
        }
        require((lstat(copy).st_mode & 0777) == mode, "open changed existing permissions");
        require(::unlink(source.c_str()) == 0 && ::unlink(copy.c_str()) == 0, "cannot remove copy fixtures");
    }
    directory.close();
    deletePath(root);
}
