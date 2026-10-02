#include "nix/cmd/legacy.hh"
#include "nix/main/shared.hh"
#include "nix/util/error.hh"
#include "nix/util/exit.hh"

#include <iostream>

namespace nix {

RegisterLegacyCommand::Commands & RegisterLegacyCommand::commands()
{
    static Commands commands;
    return commands;
}

void showManPage(const std::string &)
{
    std::cout << "Usage: nix-store [--store URI] OPERATION [ARGS...]\n"
                 "  --add PATH...          Copy files or directories into the store\n"
                 "  --query FLAG PATH...   Query --hash, --size, --references or --requisites\n"
                 "  --dump PATH            Write a NAR to stdout\n"
                 "  --restore PATH         Read a NAR from stdin\n"
                 "  --check-validity PATH  Check store registration\n"
                 "  --version              Print the Nix version\n"
                 "Use --store /tmp/nix9 for a writable store in the guest.\n"
                 "Experimental 9front port: builds, GC and symlinks are unsupported.\n";
    throw Exit();
}

} // namespace nix

int main(int argc, char ** argv)
{
    return nix::handleExceptions(argv[0], [&] {
        nix::initNix();
        nix::RegisterLegacyCommand::commands().at("nix-store")(argc, argv);
    });
}
