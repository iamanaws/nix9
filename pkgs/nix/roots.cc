#include "nix/store/plan9-roots.hh"
#include "nix/store/local-store.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/strings.hh"

#include <limits>
#include <map>

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
