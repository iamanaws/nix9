#include "nix/store/sqlite.hh"
#include "nix/util/file-system.hh"
#include "nix/util/processes.hh"
#include <sqlite3.h>
#include <iostream>

static void require(bool condition, const char *what) {
    if (!condition) throw std::runtime_error(what);
}

static const char *path = "/tmp/nix9-store #?.sqlite";
static const char *schema =
#include "schema.sql.gen.hh"
;

static nix::SQLite openDB() {
    return nix::SQLite(path, {.mode=nix::SQLiteOpenMode::NoCreate, .useWAL=false});
}

static int64_t number(nix::SQLite &db, const char *sql) {
    nix::SQLiteStmt stmt(db, sql);
    auto row = stmt.use();
    require(row.next(), "missing database row");
    return row.getInt(0);
}

static std::string text(nix::SQLite &db, const char *sql) {
    nix::SQLiteStmt stmt(db, sql);
    auto row = stmt.use();
    require(row.next(), "missing database text");
    return row.getStr(0);
}

// Test-only fault injection into the disposable guest's real store database.
void crashSQLite(const char *database) {
    using namespace nix;
    SQLite db(database, {.mode=SQLiteOpenMode::NoCreate, .useWAL=false});
    require(text(db, "PRAGMA journal_mode") == "delete", "expected rollback journal");
    require(number(db, "SELECT count(*) FROM ValidPaths") > 0 &&
            number(db, "SELECT count(*) FROM Refs") > 0, "empty recovery fixture");
    auto before = readFile(database);
    writeFile("/tmp/nix9-db-before", before);
    SQLiteTxn txn(db);
    db.exec("UPDATE ValidPaths SET narSize=narSize+1; DELETE FROM Refs");
    require(sqlite3_db_cacheflush(db) == SQLITE_OK, "flushing uncommitted pages failed");
    require(readFile(database) != before, "uncommitted pages never reached the database");
    require(std::filesystem::file_size(std::string(database) + "-journal") > 512,
            "missing recovery journal");
    writeFile("/tmp/nix9-db-ready", "ready\n");
    // The host kills the VM here, without running SQLite's destructors.
    while (true) usleep(100000);
}

void recoverSQLite(const char *database) {
    using namespace nix;
    {
        SQLite db(database, {.mode=SQLiteOpenMode::NoCreate, .useWAL=false});
        require(text(db, "PRAGMA integrity_check") == "ok", "recovered database is corrupt");
        SQLiteStmt check(db, "PRAGMA foreign_key_check");
        require(!check.use().next(), "recovered references violate foreign keys");
    }
    require(readFile(database) == readFile("/tmp/nix9-db-before"),
            "rollback did not restore the original database bytes");
    require(!std::filesystem::exists(std::string(database) + "-journal"),
            "recovery left a hot journal");
    require(!std::filesystem::exists(std::string(database) + ".p9lock"),
            "recovery left a database lock");
    std::cout << "SQLite reboot recovery PASS\n";
}

static void checkSchema() {
    using namespace nix;
    for (auto mode : {SQLiteOpenMode::NoCreate, SQLiteOpenMode::Immutable}) {
        bool rejected = false;
        try { SQLite missing(path, {.mode=mode, .useWAL=false}); }
        catch (const Error &) { rejected = true; }
        require(rejected && !std::filesystem::exists(path), "missing database was created");
    }
    bool rejected = false;
    try { SQLite wal(path, {.useWAL=true}); }
    catch (const Error &) { rejected = true; }
    require(rejected && !std::filesystem::exists(path), "WAL request accepted");

    SQLite db(path, {.useWAL=false});
    require(text(db, "PRAGMA journal_mode") == "delete" && number(db, "PRAGMA synchronous") == 2,
            "unexpected store journal settings");
    db.exec(schema);
    SQLiteStmt insert(db, "INSERT INTO ValidPaths(path,hash,registrationTime,narSize) VALUES(?,?,?,?)");
    {
        SQLiteTxn txn(db);
        insert.use()("/nix/store/00000000000000000000000000000000-dependency")("sha256:test")
            (int64_t{123})(int64_t{100}).exec();
        require(db.getLastInsertedRowId() == 1, "last inserted id changed");
        insert.use()("/nix/store/11111111111111111111111111111111-dependent")("sha256:test")
            (int64_t{124})(int64_t{1} << 40).exec();
        require(db.getLastInsertedRowId() == 2, "statement reuse failed");
        db.exec("INSERT INTO Refs VALUES(2,1); INSERT INTO Refs VALUES(2,2); "
                "INSERT INTO DerivationOutputs VALUES(2,'out','/nix/store/output')");
        txn.commit();
    }
    {
        SQLiteStmt stmt(db, "SELECT narSize,ca FROM ValidPaths WHERE id=?");
        auto row = stmt.use();
        row(int64_t{2});
        require(row.next() && row.getInt(0) == (int64_t{1} << 40) && row.isNull(1),
                "integer or NULL value changed");
        require(!row.next(), "unexpected extra row");
    }
    db.exec("CREATE TABLE Bindings(value)");
    SQLiteStmt bind(db, "INSERT INTO Bindings VALUES(?)");
    const unsigned char blob[] = {0, 255, 10, 0};
    bind.use()(blob, sizeof blob).exec();
    bind.use().bind().exec();
    require(text(db, "SELECT hex(value) FROM Bindings WHERE rowid=1") == "00FF0A00" &&
            number(db, "SELECT count(*) FROM Bindings WHERE value IS NULL") == 1, "blob or NULL binding failed");
    try {
        SQLiteTxn txn(db);
        insert.use()("/nix/store/rollback")("sha256:test")(int64_t{125})(int64_t{0}).exec();
        throw std::runtime_error("abort transaction");
    } catch (const std::runtime_error &) { }
    require(number(db, "SELECT count(*) FROM ValidPaths") == 2, "uncommitted row survived");
    rejected = false;
    try { db.exec("DELETE FROM ValidPaths WHERE id=1"); }
    catch (const SQLiteError &e) { rejected = e.errNo == SQLITE_CONSTRAINT; }
    require(rejected, "referenced path deletion accepted");
    db.exec("DELETE FROM ValidPaths WHERE id=2");
    require(number(db, "SELECT count(*) FROM Refs") == 0 &&
            number(db, "SELECT count(*) FROM DerivationOutputs") == 0,
            "self-reference or cascading deletion failed");
}

static void blocked() {
    auto db = openDB();
    require(sqlite3_busy_timeout(db, 0) == SQLITE_OK, "setting busy timeout failed");
    bool busy = false;
    try {
        nix::SQLiteStmt stmt(db, "BEGIN IMMEDIATE");
        stmt.use().exec();
    } catch (const nix::SQLiteBusy &) { busy = true; }
    require(busy, "competing writer bypassed lock");
}

static void writer(bool killed) {
    using namespace nix;
    Pipe ready, finish;
    ready.create(); finish.create();
    Pid child = startProcess([&] {
        ready.readSide.close(); finish.writeSide.close();
        {
            auto db = openDB();
            SQLiteTxn txn(db);
            db.exec("UPDATE ValidPaths SET narSize=narSize+1 WHERE id=1");
            require(sqlite3_db_cacheflush(db) == SQLITE_OK, "flushing dirty pages failed");
            writeFull(ready.writeSide.get(), "r");
            char byte;
            readFull(finish.readSide.get(), &byte, 1);
            txn.commit();
        }
        _exit(0);
    });
    ready.writeSide.close(); finish.readSide.close();
    char byte;
    readFull(ready.readSide.get(), &byte, 1);
    blocked();
    blocked(); // Closing a rejected connection must not release the owner's lock.
    if (killed) {
        require(!statusOk(child.kill()), "killed writer reported success");
        require(std::filesystem::file_size(std::string(path) + "-journal") > 512,
                "missing recovery journal");
    } else {
        int attempts = 0;
        retrySQLite<void>([&] {
            ++attempts;
            auto db = openDB();
            sqlite3_busy_timeout(db, 0);
            try {
                SQLiteStmt begin(db, "BEGIN IMMEDIATE");
                begin.use().exec();
                db.exec("ROLLBACK");
            } catch (const SQLiteBusy &) {
                if (attempts == 1) writeFull(finish.writeSide.get(), "r");
                throw;
            }
        });
        require(attempts > 1 && statusOk(child.wait()), "busy retry did not complete");
    }
    require(!std::filesystem::exists(std::string(path) + ".p9lock"), "writer left lock marker");
    auto db = openDB();
    require(number(db, "SELECT narSize FROM ValidPaths WHERE id=1") == 101,
            "commit or killed-writer recovery failed");
    require(text(db, "PRAGMA integrity_check") == "ok", "database integrity failed");
}

static void raceWriters() {
    using namespace nix;
    Pipe ready, start;
    ready.create(); start.create();
    constexpr int commits = 200;
    Pid children[2];
    for (auto &child : children) {
        child = startProcess([&] {
            ready.readSide.close(); start.writeSide.close();
            {
                auto db = openDB();
                require(sqlite3_busy_timeout(db, 0) == SQLITE_OK, "race timeout failed");
                writeFull(ready.writeSide.get(), "r");
                char byte;
                readFull(start.readSide.get(), &byte, 1);
                for (int i = 0; i < commits; ++i) {
                    retrySQLite<void>([&] {
                        SQLiteTxn txn(db);
                        SQLiteStmt update(db, "UPDATE ValidPaths SET narSize=narSize+1 WHERE id=1");
                        update.use().exec();
                        txn.commit();
                    });
                }
            }
            _exit(0);
        });
    }
    ready.writeSide.close(); start.readSide.close();
    char bytes[2];
    readFull(ready.readSide.get(), bytes, 2);
    writeFull(start.writeSide.get(), "rr");
    for (auto &child : children) require(statusOk(child.wait()), "competing writer failed");
    auto db = openDB();
    auto count = number(db, "SELECT narSize FROM ValidPaths WHERE id=1");
    if (count != 101 + 2 * commits)
        throw std::runtime_error("competing writers: expected " + std::to_string(101 + 2 * commits)
                                 + ", got " + std::to_string(count));
    require(text(db, "PRAGMA integrity_check") == "ok", "race corrupted database");
}

static void checkReplacement() {
    using namespace nix;
    const char *name = "/tmp/nix9-moved.sqlite";
    SQLite old(name, {.useWAL=false});
    old.exec("CREATE TABLE state(value)");
    std::filesystem::rename(name, std::string(name) + ".old");
    SQLite replacement(name, {.useWAL=false});
    replacement.exec("CREATE TABLE state(value)");
    bool rejected = false;
    try { old.exec("INSERT INTO state VALUES(1)"); }
    catch (const SQLiteError &e) { rejected = e.extendedErrNo == SQLITE_READONLY_DBMOVED; }
    require(rejected && number(replacement, "SELECT count(*) FROM state") == 0,
            "open connection switched to a replacement database");
}

void checkSQLite() {
    using namespace nix;
    checkSchema();
    writer(false);
    writer(true);
    raceWriters();
    checkReplacement();
    {
        SQLite db(path, {.mode=SQLiteOpenMode::Immutable, .useWAL=false});
        require(number(db, "SELECT count(*) FROM ValidPaths") == 1, "immutable read failed");
        bool rejected = false;
        try { db.exec("DELETE FROM ValidPaths"); }
        catch (const SQLiteError &e) { rejected = e.errNo == SQLITE_READONLY; }
        require(rejected, "immutable database accepted a write");
    }
    {
        SQLite cache("/tmp/nix9-cache.sqlite", {.useWAL=false});
        cache.isCache();
        require(text(cache, "PRAGMA journal_mode") == "truncate" &&
                number(cache, "PRAGMA synchronous") == 0, "cache did not use rollback journals");
        require(text(cache, "PRAGMA journal_mode=WAL") == "truncate", "WAL unexpectedly enabled");
    }
}
