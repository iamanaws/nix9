#include "sqlite3.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static const char *path = "/tmp/nix9-sqlite.db";
static const char *vfs;
static bool native;
static char journal_path[128], lock_path[128];

static void check(bool ok, const char *what) {
    if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); std::exit(1); }
}

static void sql(sqlite3 *db, const char *query) {
    int rc = sqlite3_exec(db, query, nullptr, nullptr, nullptr);
    if (rc != SQLITE_OK) {
        std::fprintf(stderr, "%s: %d %s\n", query, rc, sqlite3_errmsg(db));
        std::exit(1);
    }
}

static sqlite3 *open_db() {
    sqlite3 *db = nullptr;
    check(sqlite3_open_v2(path, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE,
                          vfs) == SQLITE_OK, "open database");
    // No busy retry: contention and abandoned locks must be visible immediately.
    check(sqlite3_busy_timeout(db, 0) == SQLITE_OK, "busy timeout");
    return db;
}

static void close_db(sqlite3 *db) {
    check(sqlite3_close(db) == SQLITE_OK, "close database");
}

static void expect(sqlite3 *db, const char *query, const char *value) {
    sqlite3_stmt *stmt = nullptr;
    check(sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK, query);
    check(sqlite3_step(stmt) == SQLITE_ROW, "query row");
    const char *actual = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 0));
    if (!actual || std::strcmp(actual, value) != 0)
        std::fprintf(stderr, "%s: expected %s, got %s\n", query, value, actual ? actual : "NULL");
    check(actual && std::strcmp(actual, value) == 0, value);
    check(sqlite3_step(stmt) == SQLITE_DONE, "single row");
    check(sqlite3_finalize(stmt) == SQLITE_OK, "finalize");
}

static void blocked() {
    sqlite3 *db = open_db();
    check(sqlite3_exec(db, "BEGIN IMMEDIATE", nullptr, nullptr, nullptr) == SQLITE_BUSY,
          "competing writer must get SQLITE_BUSY");
    close_db(db);
}

static void transfer(int fd, bool sending) {
    char byte = 'x';
    check((sending ? write(fd, &byte, 1) : read(fd, &byte, 1)) == 1, "pipe handshake");
}

static void writer(bool crash) {
    int ready[2], finish[2];
    check(pipe(ready) == 0 && pipe(finish) == 0, "pipes");
    std::fflush(nullptr);
    pid_t pid = fork();
    check(pid >= 0, "fork");
    if (pid == 0) {
        close(ready[0]); close(finish[1]);
        sqlite3 *db = open_db();
        sql(db, "BEGIN IMMEDIATE; UPDATE state SET value=value+1");
        // Force dirty pages into the database before interruption, retaining
        // the rollback journal. An in-memory update would not test recovery.
        check(sqlite3_db_cacheflush(db) == SQLITE_OK, "flush dirty pages");
        transfer(ready[1], true);
        transfer(finish[0], false);
        sql(db, "COMMIT");
        close_db(db);
        _exit(0);
    }
    close(ready[1]); close(finish[0]);
    transfer(ready[0], false);
    blocked();
    blocked(); // Closing a rejected connection must not release the owner's lock.
    if (crash) check(kill(pid, SIGKILL) == 0, "kill writer");
    else transfer(finish[1], true);
    int status = 0;
    check(waitpid(pid, &status, 0) == pid, "wait writer");
    if (crash) {
        // cc9 maps unrecognized Plan 9 wait messages to SIGABRT, including
        // the kernel's kill message. Require abnormal termination, and report
        // the lost signal identity rather than claiming POSIX conformance.
        check(WIFSIGNALED(status), "writer terminated abnormally");
        std::printf("SIGKILL writer: waitpid reports signal %d\n", WTERMSIG(status));
    } else check(WIFEXITED(status) && WEXITSTATUS(status) == 0, "writer committed");
    close(ready[0]); close(finish[1]);
}

static void race_writers() {
    int ready[2], start[2];
    check(pipe(ready) == 0 && pipe(start) == 0, "race pipes");
    pid_t children[2];
    for (int i = 0; i < 2; ++i) {
        children[i] = fork();
        check(children[i] >= 0, "race fork");
        if (children[i] == 0) {
            close(ready[0]); close(start[1]);
            sqlite3 *db = open_db();
            check(sqlite3_busy_timeout(db, 10000) == SQLITE_OK, "race busy timeout");
            transfer(ready[1], true);
            transfer(start[0], false);
            for (int n = 0; n < 20; ++n)
                sql(db, "BEGIN IMMEDIATE; UPDATE state SET value=value+1; COMMIT");
            close_db(db);
            _exit(0);
        }
    }
    close(ready[1]); close(start[0]);
    for (int i = 0; i < 2; ++i) transfer(ready[0], false);
    for (int i = 0; i < 2; ++i) transfer(start[1], true);
    for (pid_t pid : children) {
        int status = 0;
        check(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0,
              "racing writer committed");
    }
    close(ready[0]); close(start[1]);
    sqlite3 *db = open_db();
    expect(db, "SELECT value FROM state", "44");
    expect(db, "PRAGMA integrity_check", "ok");
    close_db(db);
    std::puts("two writers, 40 committed updates PASS");
}

int main(int argc, char **argv) {
    check(argc == 2, "choose unix-dotfile or unix-plan9");
    vfs = argv[1];
    native = std::strcmp(vfs, "unix-plan9") == 0;
    check(native || std::strcmp(vfs, "unix-dotfile") == 0, "known VFS");
    if (native) path = "/tmp/nix9-sqlite-native.db";
    std::snprintf(journal_path, sizeof journal_path, "%s-journal", path);
    std::snprintf(lock_path, sizeof lock_path, "%s%s", path, native ? ".p9lock" : ".lock");
    setbuf(stdout, nullptr);
    sqlite3 *db = open_db();
    expect(db, "PRAGMA synchronous", "2");
    expect(db, "PRAGMA journal_mode=DELETE", "delete");
    sql(db, "CREATE TABLE state(value INTEGER); INSERT INTO state VALUES(1)");
    close_db(db);

    writer(false);
    db = open_db();
    expect(db, "SELECT value FROM state", "2");
    sql(db, "BEGIN IMMEDIATE; UPDATE state SET value=3; ROLLBACK");
    expect(db, "SELECT value FROM state", "2");
    close_db(db);
    std::puts("contention, commit, rollback PASS");

    writer(true);
    struct stat journal;
    check(stat(journal_path, &journal) == 0 && journal.st_size > 512,
          "rollback journal remains after kill");
    if (native) {
        check(access(lock_path, F_OK) < 0, "kernel removed dead writer's lock");
    } else {
        blocked();
        std::puts("abandoned dotfile lock blocks reopening CONFIRMED");
        // Diagnostic only: the sole owner is dead and reaped, and no other
        // connections exist. Never delete a live database's lock this way.
        check(rmdir(lock_path) == 0, "remove abandoned test lock");
    }
    db = open_db();
    expect(db, "SELECT value FROM state", "2");
    expect(db, "PRAGMA integrity_check", "ok");
    sql(db, "BEGIN IMMEDIATE; UPDATE state SET value=4; COMMIT");
    close_db(db);
    db = open_db();
    expect(db, "SELECT value FROM state", "4");
    close_db(db);
    std::puts(native ? "automatic journal recovery PASS"
                     : "journal recovery after manual lock removal PASS");
    if (native) race_writers();
    std::printf("sqlite %s probe PASS\n", vfs);
}
