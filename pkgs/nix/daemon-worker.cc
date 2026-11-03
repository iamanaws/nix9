#include "nix/store/daemon.hh"
#include "nix/store/store-open.hh"
#include "nix/store/local-store.hh"
#include "nix/util/environment-variables.hh"
#include "nix/util/serialise.hh"

namespace nix {

void runDaemonConnection()
{
    // Only the native authenticated listener sets this environment. No command
    // line received from a client is executed by the listener.
    if (!getEnv("NIX9_CLIENT_USER") || !getEnv("NIX9_BUILD_USER") || !getEnv("NIX9_BUILD_LAUNCHER"))
        throw Error("the daemon worker requires the native authenticated listener");
    auto store = openStore();
    if (!store.dynamic_pointer_cast<LocalStore>())
        throw Error("the daemon worker requires its owner's local store");
    daemon::processConnection(store, FdSource(STDIN_FILENO), FdSink(STDOUT_FILENO), NotTrusted, daemon::NotRecursive);
}

}
