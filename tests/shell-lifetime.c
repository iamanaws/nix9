/* Retain inherited shell roots, including after the launching shell exits. */
#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	char path[512], board[64], *marker, ready;
	int fd, found, n, p[2];
	Dir d;

	if(argc != 3)
		sysfatal("usage: shell-lifetime {hold|detach} directory");
	found = 0;
	for(fd = 3; fd < 256; fd++){
		if(fd2path(fd, path, sizeof path) < 0 || strcmp(path, "#s/clone") != 0)
			continue;
		found++;
		if(write(fd, "broken root\n", 12) >= 0)
			sysfatal("shell root descriptor is writable");
		snprint(path, sizeof path, "/fd/%d", fd);
		if(open(path, OWRITE) >= 0)
			sysfatal("shell root descriptor can be reopened for writing");
		nulldir(&d);
		d.mode = 0777;
		if(dirfwstat(fd, &d) >= 0)
			sysfatal("shell root lease permits metadata changes");
		n = pread(fd, board, sizeof board - 1, 0);
		if(n <= 0)
			sysfatal("read shell root lease: %r");
		board[n] = 0;
		snprint(path, sizeof path, "#s/%s/root", board);
		if(open(path, OREAD) >= 0)
			sysfatal("shell can open owner's root descriptor");
	}
	if(found != 1)
		sysfatal("expected one inherited shell root, got %d", found);
	if(strcmp(argv[1], "detach") == 0){
		if(pipe(p) < 0)
			sysfatal("pipe: %r");
		switch(rfork(RFPROC|RFNOWAIT|RFFDG|RFNOTEG)){
		case -1:
			sysfatal("rfork: %r");
		case 0:
			close(p[0]);
			close(0);
			close(1);
			close(2);
			if(write(p[1], "r", 1) != 1)
				exits("ready");
			close(p[1]);
			break;
		default:
			close(p[1]);
			if(read(p[0], &ready, 1) != 1)
				sysfatal("child did not start");
			exits(nil);
		}
	}
	marker = smprint("%s/pid", argv[2]);
	fd = create(marker, OWRITE, 0600);
	if(fd < 0 || fprint(fd, "%d\n", getpid()) < 0)
		sysfatal("record child: %r");
	close(fd);
	marker = smprint("%s/stop", argv[2]);
	while(access(marker, AEXIST) < 0)
		sleep(20);
	exits(nil);
}
