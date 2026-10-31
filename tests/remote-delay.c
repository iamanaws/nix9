#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	if(argc != 2)
		sysfatal("usage: remote-test-sleep seconds");
	sleep(atoi(argv[1]) * 1000);
	exits(nil);
}
