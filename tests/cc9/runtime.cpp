#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

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
    writeFile("/env/CC9_REGRESSION_ENV", "direct\n");
    const char *actual = getenv(key);
    check(actual && std::string(actual) == "direct\n", "getenv sees /env writes");
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

static volatile sig_atomic_t noted;
static void onNote(int) { noted = 1; }

static void polling() {
    check(poll(nullptr, 0, 0) == 0 && poll(nullptr, 0, 20) == 0, "poll timeout");
    for (int timeout : {3000, -1}) for (const char *note : {"interrupt", "hangup"}) {
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
            check(write(ready[1], "r", 1) == 1, "signal poll readiness");
            struct pollfd fd{blocked[0], POLLIN, 0};
            int result = poll(&fd, 1, timeout);
            check(result == -1 && errno == EINTR && noted, "poll interrupted by note");
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
        waitFor(child, 0);
        close(ready[0]); close(blocked[0]); close(blocked[1]);
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "return42") == 0) return 42;
    auto executable = std::filesystem::absolute(argv[0]).string();
    std::string scratch = "/tmp/cc9-tests-" + std::to_string(getpid());
    check(mkdir(scratch.c_str(), 0755) == 0 && chdir(scratch.c_str()) == 0, "test directory");
    const char *selected = argc == 2 ? argv[1] : "all";
    bool matched = false;
    for (auto [name, test] : {std::pair{"allocation", allocations}, {"environment", environment},
                            {"path", execPath}, {"copy", copies}, {"poll", polling}}) {
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
    check(matched && argc <= 2, "unknown test (allocation, environment, path, copy, poll, exit, all)");
    check(chdir("/tmp") == 0 && rmdir(scratch.c_str()) == 0, "remove test directory");
    std::puts("cc9 runtime tests PASS");
}
