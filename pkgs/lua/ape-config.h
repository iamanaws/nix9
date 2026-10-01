#ifndef LUA_APE_CONFIG_H
#define LUA_APE_CONFIG_H

#define LUA_USE_C89
#define LUA_USE_POSIX
#define _POSIX_SOURCE
#define _BSD_EXTENSION
#define _REENTRANT_SOURCE

#define LUA_PATH_DEFAULT \
  "@guestPrefix@/share/lua/5.4/?.lua;@guestPrefix@/share/lua/5.4/?/init.lua;./?.lua;./?/init.lua"

/* APE provides the ISO C entry points, not _setjmp/_longjmp. */
#define LUAI_THROW(L,c) longjmp((c)->b, 1)
#define LUAI_TRY(L,c,a) if (setjmp((c)->b) == 0) { a }
#define luai_jmpbuf jmp_buf

/* APE has no stdio locking API. This interpreter runs in one OS thread. */
#define l_getc(f) getc(f)
#define l_lockfile(f) ((void)0)
#define l_unlockfile(f) ((void)0)

#endif
