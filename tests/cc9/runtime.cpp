#include <cerrno>
#include <atomic>
#include <cmath>
#include <stdexcept>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern "C" long __real_n9_create(const char *, int, unsigned long);
extern "C" long n9_close(int);
extern "C" long __real_n9_close(int);
extern "C" long __real_n9_dup(int, int);
static std::atomic<int> watchedPollFd{-1}, retiringPollFd{-1};
static std::atomic<bool> pollFdRetired, releasePollReader;
static const char *mkdirRacePath;

extern "C" long __wrap_n9_dup(int from, int to) {
    long fd = __real_n9_dup(from, to);
    if (from == watchedPollFd.load() && to == -1 && fd >= 0)
        retiringPollFd.store(fd);
    return fd;
}

extern "C" long __wrap_n9_close(int fd) {
    int expected = fd;
    bool pause = fd >= 0 && retiringPollFd.compare_exchange_strong(expected, -1);
    long result = __real_n9_close(fd);
    if (pause) {
        // Hold the reader between closing its private fd and clearing its table
        // entry. Another thread can reuse that number and fork in this window.
        pollFdRetired.store(true);
        while (!releasePollReader.load()) usleep(1000);
    }
    return result;
}

extern "C" long __wrap_n9_create(const char *path, int mode, unsigned long permissions) {
    if (mkdirRacePath && std::strcmp(path, mkdirRacePath) == 0) {
        mkdirRacePath = nullptr;
        // Model another client creating this name between mkdir's stat and
        // create. A read-only parent reproduces CWFS's failed-create error.
        long fd = __real_n9_create(path, 0, 0x80000000UL | 0700);
        if (fd < 0) return fd;
        n9_close(fd);
        return __real_n9_create("mkdir-denied/child", mode, permissions);
    }
    return __real_n9_create(path, mode, permissions);
}

static void check(bool ok, const char *message) {
    if (!ok) { std::fprintf(stderr, "FAIL: %s (errno %d)\n", message, errno); std::exit(1); }
}

static void waitFor(pid_t child, int expected) {
    int status;
    check(child > 0 && waitpid(child, &status, 0) == child, "waitpid");
    check(WIFEXITED(status) && WEXITSTATUS(status) == expected, "child exit status");
}

static void writeFile(const char *path, const std::string &contents, mode_t mode = 0600) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, mode);
    check(fd >= 0, "open fixture");
    check(write(fd, contents.data(), contents.size()) == static_cast<ssize_t>(contents.size()), "write fixture");
    check(close(fd) == 0, "close fixture");
}

static mode_t modeOf(const char *path) {
    struct stat st;
    check(stat(path, &st) == 0, "stat fixture");
    return st.st_mode & 0777;
}

static void allocations() {
    for (size_t size : {64u, 4096u, 2097152u}) {
        for (int i = 0; i < 64; ++i) {
            auto p = static_cast<unsigned char *>(std::aligned_alloc(64, size));
            check(p && reinterpret_cast<uintptr_t>(p) % 64 == 0, "aligned_alloc");
            std::memset(p, 0x5a, size);
            if (i % 2) {
                p = static_cast<unsigned char *>(std::realloc(p, size * 2));
                check(p, "realloc aligned block");
                for (size_t j = 0; j < size; ++j) check(p[j] == 0x5a, "realloc contents");
            }
            std::free(p);
        }
    }
    struct alignas(64) Aligned { char bytes[4096]{}; };
    for (int i = 0; i < 64; ++i) {
        auto p = std::make_shared<Aligned>();
        check(reinterpret_cast<uintptr_t>(p.get()) % 64 == 0 && !p->bytes[4095], "aligned shared allocation");
    }
}

static std::atomic<bool> cacheDone;
static pthread_key_t cacheKey;

static void *cacheChild(void *) {
    static thread_local volatile int value;
    value = 37;
    check(pthread_setspecific(cacheKey, reinterpret_cast<void *>(1)) == 0, "thread-specific data");
    return nullptr;
}

static void *cacheCreator(void *) {
    // Recycling slots frees the previous worker's TLS arrays before registration.
    for (int i = 0; i < 10000; ++i) {
        pthread_t thread;
        check(pthread_create(&thread, nullptr, cacheChild, nullptr) == 0, "create cache worker");
        check(pthread_join(thread, nullptr) == 0, "join cache worker");
    }
    cacheDone.store(true);
    return nullptr;
}

static void threadAllocations() {
    check(pthread_key_create(&cacheKey, nullptr) == 0, "create cache key");
    pthread_t creator;
    check(pthread_create(&creator, nullptr, cacheCreator, nullptr) == 0, "create worker parent");
    unsigned rounds = 0;
    while (!cacheDone.load()) {
        unsigned char *blocks[64];
        for (int i = 0; i < 64; ++i) {
            blocks[i] = static_cast<unsigned char *>(std::malloc(2048));
            check(blocks[i], "allocate alongside worker registration");
            std::memset(blocks[i], i + 1, 2048);
        }
        for (int i = 0; i < 64; ++i) {
            for (int j = 0; j < 2048; ++j)
                check(blocks[i][j] == i + 1, "live allocation overwritten during worker registration");
            std::free(blocks[i]);
        }
        ++rounds;
    }
    check(pthread_join(creator, nullptr) == 0 && rounds > 0, "concurrent allocation completed");
    check(pthread_key_delete(cacheKey) == 0, "delete cache key");
}

static void math() {
    volatile double two = 2.0, negative = -1.0;
    check(std::abs(std::sqrt(two) * std::sqrt(two) - two) < 1e-14, "sqrt");
    check(std::abs(std::sin(two) - 0.9092974268256817) < 1e-14, "sin");
    check(std::isnan(std::sqrt(negative)), "sqrt domain error");
    volatile long double value = 9.0L;
    check(std::sqrt(value) == 3.0L, "long double sqrt");
}

static void exceptions() {
    int cleaned = 0;
    struct Cleanup { int &count; ~Cleanup() { ++count; } };
    bool caught = false;
    try {
        Cleanup cleanup{cleaned};
        throw std::runtime_error("runtime unwind");
    } catch (const std::runtime_error &error) {
        caught = std::strcmp(error.what(), "runtime unwind") == 0;
    }
    check(caught && cleaned == 1, "exception unwinding");
}

static void environment() {
    const char *key = "CC9_REGRESSION_ENV";
    for (const auto &value : {std::string{}, std::string("first\nlast\n"), std::string(12000, 'x')}) {
        check(setenv(key, value.c_str(), 1) == 0, "setenv");
        const char *actual = getenv(key);
        check(actual && value == actual, "getenv value");
        check(setenv(key, "replacement", 0) == 0, "setenv without overwrite");
        actual = getenv(key);
        check(actual && value == actual, "setenv preserved value");
    }
    writeFile("/env/CC9_REGRESSION_ENV", std::string("direct\n\0", 8));
    const char *actual = getenv(key);
    check(actual && std::string(actual) == "direct\n", "getenv sees /env writes");
    writeFile("/env/CC9_REGRESSION_ENV", "direct\n");
    actual = getenv(key);
    check(actual && std::string(actual) == "direct", "getenv strips raw trailing newlines");
    check(unsetenv(key) == 0 && !getenv(key), "unsetenv");
    for (const char *name : {"", ".", "..", "../dev/pid", "/dev/pid", "a=b"}) {
        check(!getenv(name), "invalid getenv name");
        check(setenv(name, "x", 1) == -1 && errno == EINVAL, "invalid setenv name");
        check(unsetenv(name) == -1 && errno == EINVAL, "invalid unsetenv name");
    }
    std::string longName(300, 'x');
    check(!getenv(longName.c_str()), "long getenv name");
    check(setenv(longName.c_str(), "x", 1) == -1 && errno == ENAMETOOLONG, "long setenv name");
}

static void execPath() {
    check(mkdir("first", 0755) == 0 && mkdir("second", 0755) == 0, "PATH directories");
    for (auto [file, status] : {std::pair{"first/command", 17}, {"second/command", 23}, {"command", 31}}) {
        writeFile(file, "#!/bin/rc\nexit 'cc9exit=" + std::to_string(status) + "'\n");
        check(chmod(file, 0755) == 0, "PATH fixture permissions");
    }
    auto run = [](const char *path, const char *program, int expected, int error = 0) {
        pid_t child = fork();
        if (child == 0) {
            check(path ? setenv("PATH", path, 1) == 0 : unsetenv("PATH") == 0, "child PATH");
            char *args[] = {const_cast<char *>(program), nullptr};
            execvp(program, args);
            _exit(error && errno == error ? 0 : 99);
        }
        waitFor(child, expected);
    };
    run("first:second", "command", 17);
    run("second:first", "command", 23);
    run("missing:second", "command", 23);
    run("first/command:second", "command", 23);
    run("missing", "first/command", 17);
    run("missing", "cat", 0, ENOENT);
    run("first", "", 0, ENOENT);
    run(nullptr, "echo", 0);
    for (const char *path : {"", ":second", "missing::second", "missing:"}) run(path, "command", 31);
    std::string longPath;
    for (int i = 0; i < 100; ++i) longPath += "missing:";
    run((longPath + "second").c_str(), "command", 23);
    check(chmod("first/command", 0644) == 0, "permission denial fixture");
    run("first:second", "command", 23);
    run("first:missing", "command", 0, EACCES);
    run("second", "first/command", 0, EACCES);
    check(unlink("first/command") == 0 && unlink("second/command") == 0 && unlink("command") == 0,
          "remove PATH fixtures");
    check(rmdir("first") == 0 && rmdir("second") == 0, "remove PATH directories");
}

static void copies() {
    int directory = open(".", O_RDONLY);
    check(directory >= 0, "open directory");
    for (mode_t mode : {0751, 0700, 0640}) {
        writeFile("source", "#!/bin/rc\nexit\n", mode);
        check(modeOf("source") == mode, "open creation mode");
        int fd = openat(directory, "copy", O_WRONLY | O_CREAT | O_EXCL, mode);
        check(fd >= 0 && close(fd) == 0 && modeOf("copy") == mode, "openat creation mode");
        check(unlink("copy") == 0, "remove openat fixture");
        check(std::filesystem::copy_file("source", "copy"), "copy_file");
        check(modeOf("copy") == mode, "new copy permissions");
        if (mode & 0100) {
            pid_t child = fork();
            if (!child) { char *args[] = {const_cast<char *>("copy"), nullptr}; execv("./copy", args); _exit(99); }
            waitFor(child, 0);
        }
        check(chmod("copy", 0600) == 0, "change copy permissions");
        check(std::filesystem::copy_file("source", "copy", std::filesystem::copy_options::overwrite_existing),
              "overwrite copy");
        check(modeOf("copy") == mode, "overwrite permissions");
        fd = open("copy", O_WRONLY | O_CREAT | O_TRUNC, 0600);
        check(fd >= 0 && close(fd) == 0 && modeOf("copy") == mode, "preserve existing mode");
        check(unlink("source") == 0 && unlink("copy") == 0, "remove copy fixtures");
    }
    check(close(directory) == 0, "close directory");
}

static void directories() {
    check(mkdir("mkdir-denied", 0500) == 0, "directory permission fixture");
    mkdirRacePath = "raced";
    check(mkdir("raced", 0755) == -1 && errno == EEXIST, "mkdir concurrent creation");
    check(!mkdirRacePath && modeOf("raced") == 0700, "preserve concurrently created directory");
    check(rmdir("raced") == 0, "remove raced directory");

    mkdirRacePath = "parent";
    std::error_code error;
    check(std::filesystem::create_directories("parent/child", error) && !error,
          "create_directories concurrent parent creation");
    check(!mkdirRacePath && modeOf("parent") == 0700, "preserve concurrently created parent");
    check(rmdir("parent/child") == 0 && rmdir("parent") == 0, "remove directory tree");
    check(mkdir("mkdir-denied/child", 0755) == -1 && errno == EACCES,
          "preserve genuine directory permission denial");
    check(chmod("mkdir-denied", 0700) == 0 && rmdir("mkdir-denied") == 0,
          "remove directory permission fixture");
}

static volatile sig_atomic_t noted;
static void onNote(int) { noted = 1; }

static void polling() {
    check(poll(nullptr, 0, 0) == 0 && poll(nullptr, 0, 20) == 0, "poll timeout");
    for (int timeout : {3000, -1, 0}) for (const char *note : {"interrupt", "hangup"}) {
        int ready[2], blocked[2];
        check(pipe(ready) == 0 && pipe(blocked) == 0, "poll pipes");
        pid_t child = fork();
        if (!child) {
            struct sigaction action{};
            action.sa_handler = onNote;
            sigemptyset(&action.sa_mask);
            check(sigaction(SIGINT, &action, nullptr) == 0 && sigaction(SIGHUP, &action, nullptr) == 0,
                  "install note handlers");
            noted = 0;
            struct pollfd fd{blocked[0], POLLIN, 0};
            if (timeout == 0) check(poll(&fd, 1, 0) == 0, "start buffered reader");
            check(write(ready[1], "r", 1) == 1, "signal poll readiness");
            char byte;
            int result = timeout == 0 ? read(blocked[0], &byte, 1) : poll(&fd, 1, timeout);
            check(result == -1 && errno == EINTR && noted, "poll or buffered read interrupted by note");
            _exit(0);
        }
        check(child > 0, "fork poll child");
        close(ready[1]);
        char byte;
        check(read(ready[0], &byte, 1) == 1, "wait for poll readiness");
        usleep(100000); // Let the child enter the blocking wait.
        std::string path = "/proc/" + std::to_string(child) + "/note";
        int fd = open(path.c_str(), O_WRONLY);
        check(fd >= 0 && write(fd, note, std::strlen(note)) == static_cast<ssize_t>(std::strlen(note)), "post note");
        close(fd);
        int status = 0;
        bool finished = false;
        for (int i = 0; i < 500; ++i) {
            if (waitpid(child, &status, WNOHANG) == child) { finished = true; break; }
            usleep(10000);
        }
        if (!finished) { kill(child, SIGKILL); waitpid(child, &status, 0); }
        check(finished && WIFEXITED(status) && WEXITSTATUS(status) == 0,
              "interrupted poll or buffered read returned promptly");
        close(ready[0]); close(blocked[0]); close(blocked[1]);
    }
}

static void forkDescriptors() {
    writeFile("fork-input", "inherited-input");
    int savedInput = dup(STDIN_FILENO);
    int input = open("fork-input", O_RDONLY | O_CLOEXEC);
    check(savedInput >= 0 && input >= 0, "open fork input");
    check(dup2(input, STDIN_FILENO) == STDIN_FILENO, "install fork input");
    close(input);
    pid_t child = fork();
    if (!child) {
        char contents[32];
        ssize_t n = read(STDIN_FILENO, contents, sizeof(contents));
        check(n == 15 && std::memcmp(contents, "inherited-input", 15) == 0,
              "fork preserves standard input after poll table initialization");
        _exit(0);
    }
    waitFor(child, 0);
    check(dup2(savedInput, STDIN_FILENO) == STDIN_FILENO, "restore standard input");
    close(savedInput);
    check(unlink("fork-input") == 0, "remove fork input");
}

static void forkPollReader() {
    writeFile("fork-sentinel", "sentinel");
    int sentinel = open("fork-sentinel", O_RDONLY);
    int stream[2];
    check(sentinel >= 0 && pipe(stream) == 0, "fork race fixtures");
    watchedPollFd.store(stream[0]);
    struct pollfd fd{stream[0], POLLIN, 0};
    check(poll(&fd, 1, 0) == 0, "start poll reader");
    int retired = retiringPollFd.load();
    check(retired >= 0, "capture private reader descriptor");
    watchedPollFd.store(-1);
    close(stream[1]);
    for (int i = 0; i < 5000 && !pollFdRetired.load(); ++i) usleep(1000);
    check(pollFdRetired.load(), "reader reached descriptor retirement");
    check(__real_n9_dup(sentinel, retired) == retired, "reuse retired descriptor");
    pthread_t release;
    check(pthread_create(&release, nullptr, [](void *) -> void * {
        usleep(200000);
        releasePollReader.store(true);
        return nullptr;
    }, nullptr) == 0, "release reader thread");
    pid_t child = fork();
    if (!child) {
        char contents[8];
        check(read(retired, contents, sizeof(contents)) == 8 &&
              std::memcmp(contents, "sentinel", 8) == 0,
              "fork does not close a reused poll descriptor");
        _exit(0);
    }
    waitFor(child, 0);
    check(pthread_join(release, nullptr) == 0, "join reader release");
    close(retired); close(sentinel); close(stream[0]);
    check(unlink("fork-sentinel") == 0, "remove fork sentinel");
}

void checkProcessCleanup();

int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "return42") == 0) return 42;
    auto executable = std::filesystem::absolute(argv[0]).string();
    std::string scratch = "/tmp/cc9-tests-" + std::to_string(getpid());
    check(mkdir(scratch.c_str(), 0755) == 0 && chdir(scratch.c_str()) == 0, "test directory");
    const char *selected = argc == 2 ? argv[1] : "all";
    bool matched = false;
    for (auto [name, test] : {std::pair{"allocation", allocations}, {"threads", threadAllocations}, {"environment", environment},
                            {"path", execPath}, {"copy", copies}, {"mkdir", directories}, {"poll", polling},
                            {"fork", forkDescriptors}, {"fork-race", forkPollReader}, {"notifier", checkProcessCleanup},
                            {"math", math}, {"exceptions", exceptions}}) {
        if (std::strcmp(selected, "all") && std::strcmp(selected, name)) continue;
        matched = true;
        test();
        std::printf("PASS: %s\n", name);
    }
    if (!std::strcmp(selected, "all") || !std::strcmp(selected, "exit")) {
        matched = true;
        pid_t child = fork();
        if (!child) {
            char *args[] = {executable.data(), const_cast<char *>("return42"), nullptr};
            execv(args[0], args); _exit(99);
        }
        waitFor(child, 42);
        std::puts("PASS: exit");
    }
    check(matched && argc <= 2, "unknown test (allocation, threads, environment, path, copy, mkdir, poll, fork, fork-race, notifier, math, exceptions, exit, all)");
    check(chdir("/tmp") == 0 && rmdir(scratch.c_str()) == 0, "remove test directory");
    std::puts("cc9 runtime tests PASS");
}
