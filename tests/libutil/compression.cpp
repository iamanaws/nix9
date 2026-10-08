#include "nix/util/compression.hh"
#include "nix/util/file-system.hh"
#include <fstream>
#include <stdexcept>

void checkCompression(const char *method, const char *input, const char *host, const char *output) {
    auto data = nix::readFile(input);
    auto encoded = nix::readFile(host);
    auto check = [](bool ok) {
        if (!ok) throw std::runtime_error("compression check failed");
    };
    check(nix::decompress(method, encoded) == data);

    nix::StringSink compressed;
    auto compressor = nix::makeCompressionSink(nix::parseCompressionAlgo(method), compressed);
    for (size_t pos = 0; pos < data.size(); pos += 4093)
        (*compressor)(std::string_view(data).substr(pos, 4093));
    compressor->finish();
    check(nix::decompress(method, compressed.s) == data);

    nix::StringSink restored;
    auto decoder = nix::makeDecompressionSink(method, restored);
    for (size_t pos = 0; pos < encoded.size(); pos += 97)
        (*decoder)(std::string_view(encoded).substr(pos, 97));
    decoder->finish();
    check(restored.s == data);

    // A partial stream must fail, including when finish() needs more input.
    bool rejected = false;
    try { nix::decompress(method, std::string_view(encoded).substr(0, encoded.size() / 2)); }
    catch (const nix::Error &) { rejected = true; }
    check(rejected);

    if (std::string_view(method) == "br") {
        for (size_t size : {size_t{0}, encoded.size() - 1}) {
            auto partial = std::string_view(encoded).substr(0, size);
            rejected = false;
            try { nix::decompress(method, partial); }
            catch (const nix::CompressionError &) { rejected = true; }
            check(rejected);

            nix::StringSink sink;
            auto truncated = nix::makeDecompressionSink(method, sink);
            rejected = false;
            try {
                for (size_t pos = 0; pos < partial.size(); pos += 97)
                    (*truncated)(partial.substr(pos, 97));
                truncated->finish();
            } catch (const nix::CompressionError &) { rejected = true; }
            check(rejected);
        }
    }

    std::ofstream out(output, std::ios::binary);
    out.write(compressed.s.data(), compressed.s.size());
    out.close();
    check(bool(out));
}
