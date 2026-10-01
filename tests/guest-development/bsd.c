#define _POSIX_SOURCE 1
#define _BSD_EXTENSION 1
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct Layout {
	char first;
	uint64_t value;
};

int
main(void)
{
	FILE *pipe;
	char buf[64];

	if(sizeof(uint64_t) != 8 || offsetof(struct Layout, value) != 8)
		return 1;
	pipe = popen("/bin/echo installed-ape", "r");
	if(pipe == NULL)
		return 1;
	if(fgets(buf, sizeof buf, pipe) == NULL || strcmp(buf, "installed-ape\n") != 0)
		return 1;
	if(pclose(pipe) != 0)
		return 1;
	puts("PASS: APE headers and BSD subprocess I/O");
	return 0;
}
