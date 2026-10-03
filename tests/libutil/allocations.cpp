#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <memory>
#include <stdexcept>

void checkAllocations()
{
    // Exercise small caches, large size classes and the K&R fallback.
    for (size_t size : {64u, 4096u, 2097152u}) {
        for (int i = 0; i < 64; ++i) {
            auto p = static_cast<unsigned char *>(std::aligned_alloc(64, size));
            if (!p || reinterpret_cast<uintptr_t>(p) % 64)
                throw std::runtime_error("aligned allocation failed");
            std::memset(p, 0x5a, size);
            if (i % 2) {
                auto grown = static_cast<unsigned char *>(std::realloc(p, size * 2));
                if (!grown) throw std::runtime_error("aligned reallocation failed");
                p = grown;
                for (size_t j = 0; j < size; ++j)
                    if (p[j] != 0x5a) throw std::runtime_error("reallocation lost data");
            }
            std::free(p);
        }
    }
    // Upstream nix-instantiate heap-allocates its over-aligned EvalState.
    struct alignas(64) Aligned { char data[4096]{}; };
    for (int i = 0; i < 64; ++i) {
        auto p = std::make_shared<Aligned>();
        if (reinterpret_cast<uintptr_t>(p.get()) % 64 || p->data[4095])
            throw std::runtime_error("over-aligned shared allocation failed");
    }
}
