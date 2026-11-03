#pragma once

#include "nix/store/store-api.hh"

namespace nix {

inline constexpr std::string_view plan9RootsFeature = "nix9-roots-v1";

struct Plan9RootStore
{
    virtual ~Plan9RootStore() = default;
    virtual std::string rootOperation(std::string_view action, const Strings & args) = 0;
};

std::string plan9RootOperation(Store & store, std::string_view action, const Strings & args);
std::filesystem::path plan9RootsDirectory(Store & store);
void checkPlan9Root(Store & store, const std::filesystem::path & root);

}
