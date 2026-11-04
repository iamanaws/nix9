#pragma once

#include "nix/store/store-api.hh"

namespace nix {

inline constexpr std::string_view plan9RootsFeature = "nix9-roots-v1";
inline constexpr std::string_view plan9ShellRootFeature = "nix9-shell-root-v1";

struct Plan9RootStore
{
    virtual ~Plan9RootStore() = default;
    virtual std::string rootOperation(std::string_view action, const Strings & args) = 0;
    virtual AutoCloseFD shellRoot(const StorePath & path, const std::filesystem::path & root) = 0;
};

AutoCloseFD createPlan9ShellRoot(Store & store, const StorePath & path, const std::filesystem::path & root);

struct Plan9ShellRootTransfer
{
    AutoCloseFD lease;
    std::string service;
};

Plan9ShellRootTransfer postPlan9ShellRoot(Store & store, const StorePath & path, const std::filesystem::path & root);

std::string plan9RootOperation(Store & store, std::string_view action, const Strings & args);
std::filesystem::path plan9RootsDirectory(Store & store);
void checkPlan9Root(Store & store, const std::filesystem::path & root);

}
