/* Experimental rollback-journal locking for the pinned hjfs guest.
 * All lock levels exclude other connections, as with unix-dotfile.
 * OEXCL makes acquisition atomic; ORCLOSE removes the marker at final close,
 * including process death. Do not mix this VFS with other lock modes.
 * Forked children can retain the descriptor; power loss can leave the marker.
 * Included by sqlite3.c so the ordinary Unix I/O methods remain unchanged.
 */
extern long n9_create(const char *, int, unsigned long);
extern long n9_close(int);
extern int cc9_errno_from_errstr_or(int);
extern const char *__n9_errstr_last(int *);

/* A cached 9P mount refreshes its qid/version on open, not stat. Reopen
 * under the lock so SQLite sees other connections' committed pages. Keep
 * the original file identity: replacing an open database is not supported.
 */
static int plan9Refresh(unixFile *p){
  struct stat before, after;
  int fd, err;
  if( osFstat(p->h, &before) < 0 ) return SQLITE_IOERR_FSTAT;
  fd = robust_open(p->zPath, (p->ctrlFlags & UNIXFILE_RDONLY) ? O_RDONLY : O_RDWR, 0);
  if( fd < 0 ){
    storeLastErrno(p, errno);
    return SQLITE_IOERR_LOCK;
  }
  err = osFstat(fd, &after) < 0 ? SQLITE_IOERR_FSTAT : SQLITE_OK;
  if( err == SQLITE_OK && (before.st_dev != after.st_dev || before.st_ino != after.st_ino) )
    err = SQLITE_READONLY_DBMOVED;
  if( err != SQLITE_OK ){
    robust_close(p, fd, __LINE__);
    return err;
  }
  robust_close(p, p->h, __LINE__);
  p->h = fd;
  return SQLITE_OK;
}

static int plan9Lock(sqlite3_file *id, int level){
  unixFile *p = (unixFile *)id;
  if( p->eFileLock >= level ) return SQLITE_OK;
  if( !p->plan9LockFd ){
    /* ORDWR | OCEXEC | ORCLOSE | OEXCL. Use native flags, not cc9's
     * POSIX open wrapper, which does not expose remove-on-close. */
    long fd = n9_create((const char *)p->lockingContext, 2|32|64|0x1000, 0600);
    if( fd < 0 ){
      int err = cc9_errno_from_errstr_or(EIO);
      const char *message = __n9_errstr_last(0);
      /* Match the error reason, not "exists" inside a filename. */
      if( err == EEXIST ){
        if( (!strncmp(message, "file already exists", 19) &&
             (!message[19] || message[19] == ':')) ||
            (!strncmp(message, "file exists", 11) &&
             (!message[11] || message[11] == ':')) ) return SQLITE_BUSY;
        err = EIO;
      }
      storeLastErrno(p, err);
      return SQLITE_IOERR_LOCK;
    }
    int rc = plan9Refresh(p);
    if( rc != SQLITE_OK ){
      n9_close((int)fd);
      return rc;
    }
    p->plan9LockFd = (int)fd + 1;
  }
  p->eFileLock = level;
  return SQLITE_OK;
}

static int plan9Unlock(sqlite3_file *id, int level){
  unixFile *p = (unixFile *)id;
  if( p->eFileLock <= level ) return SQLITE_OK;
  if( level == NO_LOCK && p->plan9LockFd ){
    if( n9_close(p->plan9LockFd - 1) < 0 ) return SQLITE_IOERR_UNLOCK;
    p->plan9LockFd = 0;
  }
  p->eFileLock = level;
  return SQLITE_OK;
}

static int plan9CheckReservedLock(sqlite3_file *id, int *held){
  unixFile *p = (unixFile *)id;
  int rc;
  if( p->eFileLock != NO_LOCK ){
    *held = p->eFileLock >= RESERVED_LOCK;
    return SQLITE_OK;
  }
  /* Probe acquisition instead of treating permission or I/O errors as an
   * unlocked database. A competitor with any lock is conservatively reserved. */
  rc = plan9Lock(id, SHARED_LOCK);
  *held = rc == SQLITE_BUSY;
  if( rc == SQLITE_BUSY ) return SQLITE_OK;
  if( rc != SQLITE_OK ) return rc;
  return plan9Unlock(id, NO_LOCK);
}

static int plan9Close(sqlite3_file *id){
  unixFile *p = (unixFile *)id;
  int rc = plan9Unlock(id, NO_LOCK);
  int closed;
  sqlite3_free(p->lockingContext);
  closed = closeUnixFile(id);
  return rc == SQLITE_OK ? closed : rc;
}
