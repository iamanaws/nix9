#include "nix/expr/eval.hh"
#include "nix/expr/eval-gc.hh"
#include "nix/expr/get-drvs.hh"
#include "nix/expr/value-to-json.hh"
#include "nix/fetchers/fetch-settings.hh"
#include "nix/store/globals.hh"
#include "nix/store/store-open.hh"
#include "nix/main/shared.hh"

#include <iostream>

int main(int argc, char **argv)
{
    using namespace nix;
    return handleExceptions(argv[0], [&] {
        const char *usage = "Usage: nix-eval [--store URI] [--instantiate] (--expr EXPR | FILE)\n";
        if (argc == 2 && std::string_view(argv[1]) == "--help") {
            std::cout << usage << "Evaluate a Nix expression and print strict JSON.\n";
            return;
        }
        int i = 1;
        std::string storeUri;
        if (i + 1 < argc && std::string_view(argv[i]) == "--store") {
            storeUri = argv[i + 1];
            i += 2;
        }
        bool instantiate = i < argc && std::string_view(argv[i]) == "--instantiate";
        if (instantiate) ++i;
        bool expression = i < argc && std::string_view(argv[i]) == "--expr";
        if (expression) ++i;
        if (i + 1 != argc || (!expression && argv[i][0] == '-')) throw UsageError(usage);

        initNix();
        initGC();
        settings.readOnlyMode = !instantiate;
        EvalSettings evalSettings(settings.readOnlyMode);
        evalSettings.pureEval = false;
        fetchers::Settings fetchSettings;
        EvalState state({}, storeUri.empty() ? openStore() : openStore(storeUri), fetchSettings, evalSettings);
        Value result;
        if (expression) {
            auto expr = state.parseExprFromString(argv[i], state.rootPath(CanonPath(absPath(".").string())));
            state.eval(expr, result);
        } else {
            state.evalFile(state.rootPath(CanonPath(absPath(argv[i]).string())), result);
        }
        if (instantiate) {
            auto drv = getDerivation(state, result, false);
            if (!drv) throw Error("expected a derivation");
            std::cout << state.store->printStorePath(drv->requireDrvPath()) << '\n';
            return;
        }
        NixStringContext context;
        printValueAsJSON(state, true, result, noPos, std::cout, context);
        std::cout << '\n';
    });
}
