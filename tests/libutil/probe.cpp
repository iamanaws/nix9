#include "nix/util/archive.hh"
#include "nix/util/signals.hh"
#include "nix/util/terminal.hh"
#include "nix/util/util.hh"
#include "nix/util/signature/local-keys.hh"
#include <sodium.h>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>

void checkSQLite();
void crashSQLite(const char *database);
void recoverSQLite(const char *database);
void checkAllocations();
void checkStore();
void checkHashes(const char *input, const char *expected);
void checkProcesses(const char *executable);
void checkLocks();
void checkPathLocks(const char *executable);
int processChild(int argc, char **argv);
void checkURLs();
void checkKeys(const char *fixture, const char *input);
void checkCompression(const char *method, const char *input, const char *host, const char *output);

static void require(bool condition) {
    if (!condition) throw std::runtime_error("coroutine check failed");
}

struct Cleanup {
    int &count;
    ~Cleanup() { ++count; }
};

static void checkCoroutines() {
    // Finishing a sink delivers EOF to its reader, even after many suspensions.
    std::string payload;
    for (int i = 0; i < 65537; ++i) payload += static_cast<char>(i);
    std::string received;
    int finished = 0;
    auto sink = nix::sourceToSink([&](nix::Source &source) {
        Cleanup cleanup{finished};
        received = source.drain();
    });
    (*sink)("");
    for (size_t i = 0; i < payload.size(); i += 31)
        (*sink)(std::string_view(payload).substr(i, 31));
    sink->finish();
    require(received == payload && finished == 1);

    // Destroying either suspended adapter must unwind its coroutine stack.
    int cancelled = 0;
    {
        auto source = nix::sinkToSource([&](nix::Sink &out) {
            Cleanup cleanup{cancelled};
            out("abc");
            throw std::runtime_error("resumed cancelled writer");
        });
        char byte;
        require(source->read(&byte, 1) == 1 && byte == 'a');
    }
    require(cancelled == 1);
    {
        auto sink = nix::sourceToSink([&](nix::Source &source) {
            Cleanup cleanup{cancelled};
            source.drain();
        });
        (*sink)("x");
    }
    require(cancelled == 2);

    // Exceptions must reach the caller and destroy objects on the other stack.
    int unwound = 0;
    bool writerError = false, readerError = false;
    try {
        auto source = nix::sinkToSource([&](nix::Sink &out) {
            Cleanup cleanup{unwound};
            out("x");
            throw std::runtime_error("writer error");
        });
        source->drain();
    } catch (const std::runtime_error &e) {
        writerError = std::string_view(e.what()) == "writer error";
    }
    try {
        auto sink = nix::sourceToSink([&](nix::Source &source) {
            Cleanup cleanup{unwound};
            char bytes[2];
            source(bytes, sizeof bytes);
            throw std::runtime_error("reader error");
        });
        (*sink)("x");
        (*sink)("y");
    } catch (const std::runtime_error &e) {
        readerError = std::string_view(e.what()) == "reader error";
    }
    require(writerError && readerError && unwound == 2);
}

int main(int argc, char **argv) {
    try {
        if (argc >= 3 && std::string_view(argv[1]) == "child")
            return processChild(argc, argv);
        if (argc == 2 && std::string_view(argv[1]) == "entropy") {
            // Make the upstream fatal entropy path observable without an abort dump.
            sodium_set_misuse_handler([] {
                std::puts("entropy unavailable");
                std::fflush(stdout);
                std::_Exit(42);
            });
            nix::initLibUtil();
            nix::SecretKey::generate("entropy-test");
            std::cout << "entropy available\n";
            return 0;
        }
        nix::initLibUtil();
        if (argc == 2 && std::string_view(argv[1]) == "store") {
            checkStore();
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "allocations") {
            checkAllocations();
            std::cout << "aligned allocations PASS\n";
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "sqlite") {
            checkSQLite();
            std::cout << "libstore SQLite PASS\n";
            return 0;
        }
        if (argc == 3 && std::string_view(argv[1]) == "sqlite-crash") {
            crashSQLite(argv[2]);
            return 0;
        }
        if (argc == 3 && std::string_view(argv[1]) == "sqlite-recover") {
            recoverSQLite(argv[2]);
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "processes") {
            checkProcesses(argv[0]);
            checkLocks();
            checkPathLocks(argv[0]);
            std::cout << "libutil processes PASS\n";
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "urls") {
            checkURLs();
            std::cout << "libutil URLs PASS\n";
            return 0;
        }
        if (argc == 4 && std::string_view(argv[1]) == "keys") {
            checkKeys(argv[2], argv[3]);
            std::cout << "libutil signatures PASS\n";
            return 0;
        }
        if (argc == 6 && std::string_view(argv[1]) == "compression") {
            checkCompression(argv[2], argv[3], argv[4], argv[5]);
            std::cout << "libutil compression PASS\n";
            return 0;
        }
        if (argc == 4 && std::string_view(argv[1]) == "hashes") {
            checkHashes(argv[2], argv[3]);
            std::cout << "libutil hashes PASS\n";
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "coroutines") {
            checkCoroutines();
            std::cout << "libutil coroutines PASS\n";
            return 0;
        }
        if (argc == 2 && std::string_view(argv[1]) == "unsupported") {
            bool signals = false, pty = false;
            try { nix::unix::startSignalHandlerThread(); }
            catch (const nix::Error &) { signals = true; }
            try { nix::getPtsName(0); }
            catch (const nix::Error &) { pty = true; }
            if (!signals || !pty) return 5;
            std::cout << "unsupported features reject PASS\n";
            return 0;
        }
        if (argc != 3) return 2;
        std::ifstream in(argv[1], std::ios::binary);
        if (!in) return 2;
        std::string data((std::istreambuf_iterator<char>(in)), {});
        nix::StringSource source(data);
        nix::StringSink sink;
        nix::copyNAR(source, sink);
        if (source.pos != data.size() || sink.s != data) return 3;

        // Parse through both upstream streaming adapters with nested coroutines.
        auto pulled = nix::sinkToSource([&](nix::Sink &out) {
            for (size_t i = 0; i < data.size(); i += 7)
                out(std::string_view(data).substr(i, 7));
        });
        nix::StringSink streamed;
        auto pushed = nix::sourceToSink([&](nix::Source &in) {
            nix::copyNAR(in, streamed);
        });
        nix::copyNAR(*pulled, *pushed);
        pushed->finish();
        if (streamed.s != data) return 3;

        std::ofstream out(argv[2], std::ios::binary);
        out.write(sink.s.data(), sink.s.size());
        out.close();
        if (!out) return 4;
        std::cout << "libutil archive PASS\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
