/* Read the pinned cwfs64x configuration without opening its devices for writing. */
#include "all.h"

void
main(int argc, char **argv)
{
	char block[RBUFSIZE], *line, *next, *words[4];
	Tag *tag;
	int fd, n, mainfs, dumpfs;

	if(argc != 2)
		sysfatal("usage: cwfs-check config-device");
	fd = open(argv[1], OREAD);
	if(fd < 0 || readn(fd, block, sizeof block) != sizeof block)
		sysfatal("read configuration: %r");
	close(fd);
	tag = (Tag*)(block + BUFSIZE);
	if(tag->tag != Tconfig || tag->path != 0 || memchr(block, 0, BUFSIZE) == nil)
		sysfatal("not a provisioned cwfs64x configuration");
	mainfs = dumpfs = 0;
	for(line = block; line != nil && *line; line = next){
		next = strchr(line, '\n');
		if(next != nil)
			*next++ = 0;
		n = tokenize(line, words, nelem(words));
		if(n == 0)
			continue;
		if(strcmp(words[0], "noauth") == 0 || strcmp(words[0], "readonly") == 0)
			sysfatal("managed storage requires authentication and a writable main filesystem");
		if(n == 3 && strcmp(words[0], "filsys") == 0){
			if(strcmp(words[1], "main") == 0 && words[2][0] == 'c')
				mainfs = 1;
			if(strcmp(words[1], "dump") == 0 && strcmp(words[2], "o") == 0)
				dumpfs = 1;
		}
	}
	if(!mainfs || !dumpfs)
		sysfatal("expected cached-worm main and dump filesystems");
	exits(nil);
}
