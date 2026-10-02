#include "nix/util/url.hh"
#include <stdexcept>

static void require(bool condition) {
    if (!condition) throw std::runtime_error("URL check failed");
}

void checkURLs() {
    using namespace nix;
    auto url = parseURL("https://user:pass@example.org:8443/a%2Fb?q=x%20y#part%20one");
    require(url.scheme == "https" && url.authority->host == "example.org"
        && url.authority->user == "user" && url.authority->password == "pass"
        && url.authority->port == 8443);
    require(url.path == std::vector<std::string>({"", "a/b"})
        && url.query.at("q") == "x y" && url.fragment == "part one");
    require(parseURL(url.to_string()) == url);
    for (auto text : {"file:///tmp/archive.nar", "https://127.0.0.1:443/",
                     "http://[fe80::1%25eth0]:8080/a", "git+https://example.org/repo"}) {
        auto parsed = parseURL(text);
        require(parseURL(parsed.to_string()) == parsed);
    }
    // Upstream Nix's escaped-slash and IPv6 relative-resolution cases.
    auto base = parseURL("http://example.org:234/dir%2Ffirst/other%2Fsecond/page.html");
    require(parseURLRelative("../up.txt", base).to_string()
        == "http://example.org:234/dir%2Ffirst/up.txt");
    base = parseURL("http://[fe80::1%25eth0]:8080/dir/page.html");
    require(parseURLRelative("sub/file?x=1#part", base).to_string()
        == "http://[fe80::1%25eth0]:8080/dir/sub/file?x=1#part");
    require(fixGitURL("git@example.org:owner/repo.git").to_string()
        == "ssh://git@example.org/owner/repo.git");
    require(parseURL("https://example.org/?q=a b#x^y", true).query.at("q") == "a b");
    for (auto text : {"relative/path", "https://example.org:70000/", "https://example.org:0/",
                     "file://remote/tmp/file", "https://example.org/%zz",
                     "https://example.org/?q=a b"}) {
        bool rejected = false;
        try { parseURL(text); }
        catch (const BadURL &) { rejected = true; }
        require(rejected);
    }
}
