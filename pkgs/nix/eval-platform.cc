#include "nix/fetchers/tarball.hh"
#include "nix/util/error.hh"
namespace nix::fetchers {
ref<SourceAccessor> downloadTarball(Store &, const Settings &, const std::string &) {
    throw Error("network fetching is not supported on 9front");
}
}
