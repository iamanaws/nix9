// Bounded interoperability probe, not Nix's parser or a store implementation.
// Keep links as NAR nodes. Materialization accepts only link-free trees.
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
constexpr size_t limit = 16 * 1024 * 1024;
struct Node {
    std::string type, contents;
    bool executable = false;
    std::map<std::string, Node> entries;
};

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}

static std::string read(const fs::path &path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    auto size = in.tellg();
    require(size >= 0 && size <= limit, "file exceeds probe limit or cannot be read");
    std::string data(static_cast<size_t>(size), '\0');
    in.seekg(0);
    in.read(data.data(), data.size());
    require(bool(in), "short read");
    return data;
}

static void write(const fs::path &path, const std::string &data) {
    std::ofstream out(path, std::ios::binary);
    out.write(data.data(), data.size());
    out.close();
    if (!out) throw std::runtime_error("write failed: " + path.string());
}

struct Parser {
    const std::string &data;
    size_t offset = 0;
    std::string token() {
        require(data.size() - offset >= 8, "truncated length");
        uint64_t size = 0;
        for (int i = 0; i < 8; ++i)
            size |= uint64_t(static_cast<unsigned char>(data[offset++])) << (i * 8);
        require(size <= data.size() - offset, "truncated string");
        std::string value = data.substr(offset, size);
        offset += size;
        size_t padding = (8 - size % 8) % 8;
        require(padding <= data.size() - offset, "truncated padding");
        while (padding--) require(data[offset++] == 0, "nonzero padding");
        return value;
    }
    void want(const char *value) { require(token() == value, "unexpected NAR token"); }
    Node node(int depth = 0) {
        require(depth < 64, "tree too deep");
        want("("); want("type");
        Node n;
        n.type = token();
        if (n.type == "regular") {
            auto key = token();
            if (key == "executable") { want(""); n.executable = true; key = token(); }
            require(key == "contents", "missing contents");
            n.contents = token();
        } else if (n.type == "symlink") {
            want("target");
            n.contents = token();
            require(!n.contents.empty() && n.contents.find('\0') == std::string::npos,
                    "invalid link target");
        } else {
            require(n.type == "directory", "unknown node type");
            std::string previous;
            for (auto key = token(); key != ")"; key = token()) {
                require(key == "entry", "expected entry");
                want("("); want("name");
                auto name = token();
                require(!name.empty() && name != "." && name != ".." &&
                        name.find('/') == std::string::npos && name.find('\0') == std::string::npos,
                        "invalid entry name");
                require(previous.empty() || previous < name, "unsorted or duplicate entry");
                previous = name;
                want("node");
                n.entries.emplace(name, node(depth + 1));
                want(")");
            }
            return n;
        }
        want(")");
        return n;
    }
};

static void token(std::string &out, const std::string &s) {
    uint64_t size = s.size();
    for (int i = 0; i < 8; ++i) out += char(size >> (i * 8));
    out += s;
    out.append((8 - s.size() % 8) % 8, '\0');
}

static void encode(std::string &out, const Node &n) {
    token(out, "("); token(out, "type"); token(out, n.type);
    if (n.type == "directory") {
        for (const auto &[name, child] : n.entries) {
            token(out, "entry"); token(out, "("); token(out, "name"); token(out, name);
            token(out, "node"); encode(out, child); token(out, ")");
        }
    } else {
        if (n.executable) { token(out, "executable"); token(out, ""); }
        token(out, n.type == "symlink" ? "target" : "contents");
        token(out, n.contents);
    }
    token(out, ")");
}

static void materializable(const Node &n) {
    require(n.type != "symlink", "symlinks cannot be materialized on 9front");
    for (const auto &[name, child] : n.entries) {
        for (unsigned char c : name)
            require(c >= 32 && c != 127, "control characters cannot be materialized on 9front");
        materializable(child);
    }
}

static void extract(const Node &n, const fs::path &path) {
    if (n.type == "directory") {
        require(fs::create_directory(path), "cannot create directory");
        for (const auto &[name, child] : n.entries) extract(child, path / name);
    } else {
        write(path, n.contents);
        fs::permissions(path, n.executable ? fs::perms(0755) : fs::perms(0644));
    }
}

static Node scan(const fs::path &path, int depth = 0) {
    require(depth < 64, "tree too deep");
    auto status = fs::symlink_status(path);
    Node n;
    if (fs::is_directory(status)) {
        n.type = "directory";
        for (const auto &entry : fs::directory_iterator(path))
            n.entries.emplace(entry.path().filename().string(), scan(entry.path(), depth + 1));
    } else {
        require(fs::is_regular_file(status), "unsupported filesystem object");
        n.type = "regular";
        n.contents = read(path);
        n.executable = (status.permissions() & fs::perms::owner_exec) != fs::perms::none;
    }
    return n;
}

int main(int argc, char **argv) {
    try {
        require(argc == 4, "usage: nar-probe roundtrip|extract|dump INPUT OUTPUT");
        std::string operation = argv[1];
        require(operation == "roundtrip" || operation == "extract" || operation == "dump",
                "unknown operation");
        require(!fs::exists(argv[3]), "output already exists");
        Node n;
        if (operation == "dump") n = scan(argv[2]);
        else {
            auto data = read(argv[2]);
            Parser p{data};
            p.want("nix-archive-1");
            n = p.node();
            require(p.offset == data.size(), "trailing bytes");
        }
        if (operation == "extract") {
            materializable(n); // Reject unsupported nodes before creating any output.
            extract(n, argv[3]);
        } else {
            std::string out;
            token(out, "nix-archive-1");
            encode(out, n);
            write(argv[3], out);
        }
        std::cout << "nar " << operation << " PASS\n";
    } catch (const std::exception &error) {
        std::cerr << "nar: " << error.what() << '\n';
        return 1;
    }
}
