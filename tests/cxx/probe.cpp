#include <atomic>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>

thread_local int local = 7;

int main() {
    static_assert(__cplusplus >= 202302L);
    std::atomic<int> sum{0};
    std::vector<std::thread> workers;
    for (int i = 0; i < 4; ++i)
        workers.emplace_back([&] { sum += ++local; });
    for (auto &worker : workers) worker.join();
    if (sum != 32 || local != 7) return 1;
    int unwound = 0;
    struct Guard { int &n; ~Guard() { ++n; } };
    try {
        Guard guard{unwound};
        throw std::runtime_error("probe");
    } catch (const std::exception &) {}
    if (unwound != 1) return 2;
    std::ofstream("/tmp/cxx-file") << "nix9";
    std::string value;
    std::ifstream("/tmp/cxx-file") >> value;
    if (value != "nix9") return 3;
    std::cout << "cxx23 threads tls exceptions files PASS\n";
    std::error_code error;
    std::filesystem::create_symlink("/tmp/cxx-file", "/tmp/cxx-link", error);
    if (error) std::cout << "symlink unavailable: " << error.message() << '\n';
    else std::cout << "symlink created\n";
}
