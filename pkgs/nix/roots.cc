#include "nix/store/plan9-roots.hh"
#include "nix/store/local-store.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/strings.hh"
#include "nix/util/processes.hh"

#include <limits>
#include <map>

extern "C" long n9_create(const char *, int, unsigned long);
extern "C" long n9_open(const char *, int);
extern "C" int cc9_errno_from_errstr_or(int);

namespace nix {

std::filesystem::path plan9RootsDirectory(Store & store)
{
    if (auto remote = dynamic_cast<Plan9RootStore *>(&store))
        return remote->rootOperation("directory", {});
    auto & local = dynamic_cast<LocalStore &>(store);
    auto roots = canonPath(local.config->stateDir.get() / "gcroots");
    if (auto user = getEnv("NIX9_CLIENT_USER")) {
        // The listener sets this from factotum authentication, never client settings.
        if (user->empty() || user->size() >= 28 || user->find_first_not_of(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-") != std::string::npos
            || *user == "." || *user == "..")
            throw Error("invalid authenticated root owner");
        roots /= "per-user";
        roots /= *user;
    }
    return roots;
}

void checkPlan9Root(Store & store, const std::filesystem::path & root)
{
    auto roots = plan9RootsDirectory(store);
    if (!root.is_absolute() || root.string().find('\0') != std::string::npos
        || !isInDir(canonPath(root), roots))
        throw Error("root access denied: roots must be files below %s", PathFmt(roots));
}

AutoCloseFD createPlan9ShellRoot(Store & store, const StorePath & path, const std::filesystem::path & root)
{
    if (auto remote = dynamic_cast<Plan9RootStore *>(&store))
        return remote->shellRoot(path, root);
    checkPlan9Root(store, root);
    store.addTempRoot(path);
    if (!store.isValidPath(path))
        throw InvalidPath("cannot root invalid path '%s'", store.printStorePath(path));
    createDirs(root.parent_path());
    // The active store client excludes GC through the handoff. Never replace
    // an existing root, and give the shell only a read-only descriptor.
    // Create with OREAD | ORCLOSE | OEXCL so failure or worker death at any point
    // removes the root. A separate, short-lived descriptor fills its contents.
    // Omit OCEXEC on the read descriptor: the shell's descendants inherit it.
    AutoCloseFD fd(n9_create(root.c_str(), 64 | 0x1000, 0600));
    if (!fd) throw SysError(cc9_errno_from_errstr_or(EIO), "creating shell root");
    AutoCloseFD writer(n9_open(root.c_str(), 1 | 32));
    if (!writer) throw SysError(cc9_errno_from_errstr_or(EIO), "writing shell root");
    writeFull(writer.get(), store.printStorePath(path) + '\n');
    return fd;
}

Plan9ShellRootTransfer postPlan9ShellRoot(Store & store, const StorePath & path, const std::filesystem::path & root)
{
    auto fd = createPlan9ShellRoot(store, path, root);
    auto user = getEnv("NIX9_CLIENT_USER");
    if (!user) throw Error("shell root transfer requires an authenticated user");
    // Keep the owner's filesystem descriptor in a private board. Even an
    // OREAD descriptor could carry its owner's wstat privileges over 9P.
    // Give the client only this board's lease: it cannot be written or wstatted.
    AutoCloseFD keeper(n9_open("#s/clone", 32 /* OREAD | OCEXEC */));
    if (!keeper) throw SysError(cc9_errno_from_errstr_or(EIO), "creating shell root lease");
    // Clone leases support reads, but have no directory entry to stat.
    auto privateBoard = "#s/" + drainFD(keeper.get());
    chmod(privateBoard, 0700);
    AutoCloseFD held(n9_create((privateBoard + "/root").c_str(), 1 | 32 | 0x1000, 0600));
    if (!held) throw SysError(cc9_errno_from_errstr_or(EIO), "holding shell root");
    writeFull(held.get(), std::to_string(fd.get()));
    held.close();
    // Closing the clone lease removes every entry even after ownership changes,
    // including if the worker dies before the client acknowledges the handoff.
    AutoCloseFD lease(n9_open("#s/clone", 32 /* OREAD | OCEXEC */));
    if (!lease) throw SysError(cc9_errno_from_errstr_or(EIO), "creating shell root transfer");
    auto board = "#s/" + drainFD(lease.get());
    chmod(board, 0700);
    auto service = board + "/nix-shell";
    AutoCloseFD posted(n9_create(service.c_str(), 1 | 32 | 0x1000, 0444));
    if (!posted) throw SysError(cc9_errno_from_errstr_or(EIO), "posting shell root");
    writeFull(posted.get(), std::to_string(keeper.get()));
    posted.close();
    // Only the authenticated user can receive the posted lifetime handle.
    // Native srv permits its owner to assign the directory to another user.
    chmod(board, 0500);
    runProgram("/bin/chgrp", false, {"-u", *user, board});
    return {std::move(lease), std::move(service)};
}

static StorePath environmentPath(Store & store, const std::string & path)
{
    auto result = store.parseStorePath(path);
    store.addTempRoot(result);
    if (!store.isValidPath(result) || !std::filesystem::is_regular_file(std::filesystem::path(path) / "activate"))
        throw Error("expected a built environment: %s", path);
    return result;
}

static std::string readRoot(Store & store, const std::filesystem::path & root)
{
    auto value = readFile(root);
    if (value.empty() || value.back() != '\n') throw Error("invalid environment root: %s", PathFmt(root));
    value.pop_back();
    environmentPath(store, value);
    return value;
}

std::string plan9RootOperation(Store & store, std::string_view action, const Strings & args)
{
    if (auto remote = dynamic_cast<Plan9RootStore *>(&store))
        return remote->rootOperation(action, args);
    auto & local = dynamic_cast<LocalStore &>(store);
    if (action == "directory" && args.empty()) return plan9RootsDirectory(store).string();
    if (action == "remove" && args.size() == 1) {
        checkPlan9Root(store, args.front());
        auto root = canonPath(args.front());
        if (!std::filesystem::is_regular_file(root)) throw Error("expected a root file: %s", PathFmt(root));
        // This open store connection excludes collection by another client.
        std::filesystem::remove(root);
        return "";
    }
    if (action != "profile" || (args.size() != 2 && args.size() != 3))
        throw UsageError("usage: nix-profile ROOT {set ENVIRONMENT | list | rollback | delete NUMBER}");
    auto arg = args.begin();
    std::filesystem::path root = *arg++;
    auto operation = *arg++;
    auto value = arg == args.end() ? "" : *arg;
    if ((operation == "set" || operation == "delete") ? args.size() != 3
        : (operation != "list" && operation != "rollback") || args.size() != 2)
        throw UsageError("invalid profile action or arguments");
    checkPlan9Root(store, root);
    root = canonPath(root);

    // Serialize whole profile transactions across connections. The kernel
    // removes the lock on close or process death, including a killed client.
    auto key = hashString(HashAlgorithm::SHA256, local.config->storeDir + "\n" + root.string());
    PathLocks lock({"#s/nix9-profile-" + key.to_string(HashFormat::Base16, false)});
    auto generations = root.string() + ".generations";
    std::string current;
    if (pathExists(root)) current = readRoot(store, root);
    std::map<uint64_t, std::string> history;
    uint64_t highest = 0, selected = 0;
    if (pathExists(generations))
        for (auto & entry : DirectoryIterator{generations}) {
            auto name = entry.path().filename().string();
            auto id = string2Int<uint64_t>(name);
            if (!entry.is_regular_file() || !id || *id == 0 || std::to_string(*id) != name)
                throw Error("invalid generation: %s", PathFmt(entry.path()));
            auto target = readRoot(store, entry.path());
            history.emplace(*id, target);
            highest = std::max(highest, *id);
            if (target == current) selected = std::max(selected, *id);
        }
    auto retain = [&](const std::string & target) {
        if (highest == std::numeric_limits<uint64_t>::max()) throw Error("profile generation overflow");
        auto id = ++highest;
        local.addPermRoot(environmentPath(store, target), std::filesystem::path(generations) / std::to_string(id));
        history.emplace(id, target);
    };
    if (operation == "set") {
        auto target = environmentPath(store, value);
        if (!selected && !current.empty()) retain(current);
        if (std::none_of(history.begin(), history.end(), [&](auto & item) { return item.second == value; }))
            retain(value);
        local.addPermRoot(target, root);
    } else if (operation == "list") {
        std::string result;
        for (auto & [id, target] : history)
            result += std::to_string(id) + (id == selected ? " * " : "   ") + target + "\n";
        return result;
    } else if (operation == "rollback") {
        auto previous = history.lower_bound(selected);
        if (previous == history.begin()) throw Error("no previous generation");
        local.addPermRoot(environmentPath(store, (--previous)->second), root);
    } else {
        auto id = string2Int<uint64_t>(value);
        if (!id || !history.contains(*id) || std::to_string(*id) != value)
            throw Error("unknown generation: %s", value);
        if (*id == selected) throw Error("cannot delete the current generation");
        std::filesystem::remove(std::filesystem::path(generations) / value);
    }
    return "";
}

}
