#include "nix/util/hash.hh"
#include <fstream>
#include <iterator>
#include <stdexcept>

void checkHashes(const char *input, const char *expected) {
    std::ifstream in(input, std::ios::binary), cases(expected);
    if (!in || !cases) throw std::runtime_error("cannot read hash fixtures");
    std::string data((std::istreambuf_iterator<char>(in)), {});
    nix::experimentalFeatureSettings.set("experimental-features", "blake3-hashes");
    size_t count;
    if (!(cases >> count) || !count) throw std::runtime_error("empty hash manifest");
    for (size_t i = 0; i < count; ++i) {
        size_t size;
        std::string name, hex, nix32, base64, sri;
        if (!(cases >> size >> name >> hex >> nix32 >> base64 >> sri) || size > data.size())
            throw std::runtime_error("invalid hash fixture");
        auto check = [&](bool ok) {
            if (!ok) throw std::runtime_error(name + " hash mismatch at " + std::to_string(size) + " bytes");
        };
        auto algo = nix::parseHashAlgo(name);
        auto bytes = std::string_view(data).substr(0, size);
        auto hash = nix::hashString(algo, bytes);
        check(hash.to_string(nix::HashFormat::Base16, false) == hex);
        check(hash.to_string(nix::HashFormat::Nix32, false) == nix32);
        check(hash.to_string(nix::HashFormat::Base64, false) == base64);
        check(hash.to_string(nix::HashFormat::SRI, true) == sri);
        check(nix::Hash::parseAny(hex, algo) == hash);
        check(nix::Hash::parseAny(nix32, algo) == hash);
        check(nix::Hash::parseSRI(sri) == hash);

        nix::HashSink sink(algo);
        for (size_t pos = 0; pos < size; pos += 97) {
            sink(bytes.substr(pos, 97));
            if (pos == 0) {
                auto snapshot = sink.currentHash();
                check(snapshot.hash == nix::hashString(algo, bytes.substr(0, 97)));
                check(snapshot.numBytesDigested == bytes.substr(0, 97).size());
            }
        }
        auto result = sink.finish();
        check(result.hash == hash && result.numBytesDigested == size);
        if (size == data.size()) check(nix::hashFile(algo, input) == hash);
    }
}
