#include "nix/store/daemon.hh"
#include "nix/store/store-open.hh"
#include "nix/store/local-store.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/serialise.hh"
#include "nix/util/config-global.hh"

#include <algorithm>

namespace nix {

// The upstream authorization settings live in its Unix daemon entry point.
// Register them in every native command so all clients can read the same nix.conf.
static struct AuthorizationSettings : Config
{
    Setting<Strings> allowedUsers{this, {"*"}, "allowed-users", "Users allowed to connect to the daemon."};
    Setting<Strings> trustedUsers{this, {}, "trusted-users", "Privileged daemon users (not yet supported on Plan 9)."};
} authorizationSettings;

static GlobalConfig::Register rAuthorizationSettings(&authorizationSettings);

void runDaemonConnection()
{
    // Only the native authenticated listener sets this environment. No command
    // line received from a client is executed by the listener.
    if (!getEnv("NIX9_CLIENT_USER") || !getEnv("NIX9_BUILD_USER") || !getEnv("NIX9_BUILD_LAUNCHER"))
        throw Error("the daemon worker requires the native authenticated listener");
    // These settings are loaded by initNix(), before any client protocol data.
    // Reject unsupported policy rather than silently granting different rights.
    if (!authorizationSettings.trustedUsers.get().empty())
        throw Error("trusted-users must be empty: privileged daemon connections are not yet supported on Plan 9");
    const auto & allowed = authorizationSettings.allowedUsers.get();
    if (std::ranges::any_of(allowed, [](const auto & entry) { return entry.starts_with("@"); }))
        throw Error("allowed-users: @group selectors are not yet supported on Plan 9");
    auto user = *getEnv("NIX9_CLIENT_USER");
    if (user == "none" || (std::ranges::find(allowed, "*") == allowed.end()
        && std::ranges::find(allowed, user) == allowed.end()))
        throw Error("user '%s' is not allowed to connect to the Nix daemon", user);
    auto store = openStore();
    if (!store.dynamic_pointer_cast<LocalStore>())
        throw Error("the daemon worker requires its owner's local store");
    daemon::processConnection(store, FdSource(STDIN_FILENO), FdSink(STDOUT_FILENO), NotTrusted, daemon::NotRecursive);
}

}
