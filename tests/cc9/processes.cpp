#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <pthread.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

extern "C" void cc9_wait_stats(int *, int *, int *);

static void require(bool ok, const char *message) {
    if (!ok) { std::fprintf(stderr, "FAIL: %s\n", message); std::exit(1); }
}

template<typename Predicate> static bool until(Predicate predicate) {
    for (int i = 0; i < 300; ++i) {
        if (predicate()) return true;
        usleep(10000);
    }
    return false;
}

static bool gone(pid_t pid) {
    return access(("/proc/" + std::to_string(pid)).c_str(), F_OK) == -1;
}

static void collected(pid_t pid, int expected) {
    int status = 0;
    require(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == expected,
            "preserve child exit status");
}

static bool idle() {
    int pending, running;
    cc9_wait_stats(nullptr, &pending, &running);
    return pending == 0 && running == 0;
}

static std::atomic<pid_t> notifier;
static void childExited(int) { notifier.store(getpid()); }

void checkProcessCleanup() {
    // Keep the notifier's kernel PID so a killed owner cannot hide its orphan.
    for (bool reap : {false, true}) {
        int ready[2];
        require(pipe(ready) == 0, "notifier readiness pipe");
        pid_t owner = fork();
        if (owner == 0) {
            close(ready[0]);
            struct sigaction action{};
            action.sa_handler = childExited;
            sigemptyset(&action.sa_mask);
            require(sigaction(SIGCHLD, &action, nullptr) == 0, "install child notifier");
            notifier.store(0);
            pid_t child = fork();
            if (child == 0) _exit(23);
            require(child > 0 && until([] { return notifier.load() > 0; }), "receive child notification");
            pid_t helper = notifier.load();
            if (reap) collected(child, 23);
            require(write(ready[1], &helper, sizeof helper) == sizeof helper, "report notifier PID");
            for (;;) usleep(100000);
        }
        require(owner > 0, "fork notifier owner");
        close(ready[1]);
        pid_t helper = 0;
        require(read(ready[0], &helper, sizeof helper) == sizeof helper && helper > 1, "read notifier PID");
        close(ready[0]);
        require(kill(owner, SIGKILL) == 0, "kill notifier owner");
        int status;
        require(waitpid(owner, &status, 0) == owner && WIFSIGNALED(status), "collect killed owner");
        bool stopped = until([&] { return gone(helper); });
        if (!stopped) kill(helper, SIGKILL);
        require(stopped, "child notifier exits after its owner is killed");
        require(until(idle), "idle notifier stops after reaping");
    }

    auto descriptors = [] {
        size_t count = 0;
        for (const auto &entry : std::filesystem::directory_iterator("/fd")) { (void)entry; ++count; }
        return count;
    };
    auto before = descriptors();
    struct sigaction action{}, previous{};
    action.sa_handler = childExited;
    sigemptyset(&action.sa_mask);
    require(sigaction(SIGCHLD, &action, &previous) == 0, "install restart notifier");
    for (int i = 0; i < 3; ++i) {
        notifier.store(0);
        pid_t child = fork();
        if (child == 0) _exit(17 + i);
        require(child > 0 && until([] { return notifier.load() > 0; }), "restart child notifications");
        pid_t helper = notifier.load();
        collected(child, 17 + i);
        require(until(idle) && until([&] { return gone(helper); }), "restarted notifier exits when idle");
    }

    // A short-lived forking thread must not stop another parent's notifications.
    int finish[2];
    require(pipe(finish) == 0, "live parent's child pipe");
    std::atomic<pid_t> orphan{0};
    std::atomic<bool> leave{false};
    struct Context { std::atomic<pid_t> &child; std::atomic<bool> &leave; } context{orphan, leave};
    pthread_t parent;
    require(pthread_create(&parent, nullptr, [](void *arg) -> void * {
        auto &context = *static_cast<Context *>(arg);
        pid_t child = fork();
        if (child == 0) { usleep(100000); _exit(31); }
        require(child > 0, "fork from worker thread");
        context.child.store(child);
        while (!context.leave.load()) usleep(1000);
        return nullptr;
    }, &context) == 0, "start second forking parent");
    require(until([&] { return orphan.load() > 0; }), "worker fork completed");
    pid_t child = fork();
    if (child == 0) {
        char byte;
        require(read(finish[0], &byte, 1) == 1, "release live parent's child");
        _exit(29);
    }
    require(child > 0, "fork from main while worker owns a child");
    leave.store(true);
    require(pthread_join(parent, nullptr) == 0, "join short-lived parent");
    require(until([] { int pending; cc9_wait_stats(nullptr, &pending, nullptr); return pending == 1; }),
            "forget children whose forking parent exited");
    require(until([&] { return gone(orphan.load()); }), "orphan fixture exited");
    notifier.store(0);
    require(write(finish[1], "x", 1) == 1, "finish live parent's child");
    require(until([] { return notifier.load() > 0; }), "live parent still receives child notifications");
    collected(child, 29);
    close(finish[0]); close(finish[1]);
    require(until(idle), "last parent releases notifier");
    require(descriptors() == before, "parent status descriptors do not leak across forks");
    require(sigaction(SIGCHLD, &previous, nullptr) == 0, "restore child handler");
}
