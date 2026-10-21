#include <u.h>
#include <libc.h>

void
main(void)
{
	char *s;
	char *expected = "native libc 42";
	char *unicode = "Plan 9 αβ";
	char *payload = "answer42";
	int fd;
	char buf[8];
	char filename[64];

	s = smprint("%s %d", "native libc", 42);
	assert(strcmp(s, expected) == 0);
	free(s);
	assert(toupperrune(L'α') == L'Α');
	assert(isalpharune(L'β'));
	assert(utflen(unicode) == 9);
	snprint(filename, sizeof filename, "/tmp/nix9-libc-%d", getpid());
	fd = create(filename, ORDWR|ORCLOSE, 0600);
	assert(fd >= 0);
	assert(write(fd, payload, 8) == 8);
	assert(seek(fd, 6, 0) == 6);
	assert(read(fd, buf, sizeof buf) == 2);
	assert(memcmp(buf, payload+6, 2) == 0);
	close(fd);
	print("native libc PASS\n");
	exits(nil);
}
