#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	int i;

	if(argc != 2)
		sysfatal("usage: configuration-wait path");
	for(i = 0; i < 3000; i++){
		if(access(argv[1], AREAD) == 0)
			exits(nil);
		sleep(100);
	}

	sysfatal("configuration test was not released");
}
