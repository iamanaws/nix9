/* Keep an output descriptor after leaving the builder's note group. */
#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	char *path, ready;
	int fd, pid, p[2];

	if(argc != 2)
		sysfatal("usage: shared-detached output");
	path = smprint("/proc/%d/ctl", getppid());
	if(open(path, OWRITE) >= 0)
		sysfatal("anonymous builder can control another process");
	path = smprint("/proc/%d/fd", getppid());
	if(open(path, OREAD) >= 0)
		sysfatal("anonymous builder can inspect another process's descriptors");
	path = smprint("%s/live", argv[1]);
	fd = create(path, ORDWR, 0600);
	if(fd < 0 || write(fd, "x\n", 2) != 2 || pipe(p) < 0)
		sysfatal("prepare detached writer: %r");
	pid = rfork(RFPROC|RFNOWAIT|RFFDG|RFNOTEG);
	if(pid < 0)
		sysfatal("fork detached writer: %r");
	if(pid == 0){
		close(0);
		close(1);
		close(2);
		close(p[0]);
		if(write(p[1], "r", 1) != 1)
			exits("ready");
		close(p[1]);
		while(pwrite(fd, "x", 1, 0) == 1)
			sleep(20);
		exits(nil);
	}
	close(p[1]);
	if(read(p[0], &ready, 1) != 1)
		sysfatal("detached writer did not start");
	close(p[0]);
	close(fd);
	path = smprint("%s/pid", argv[1]);
	fd = create(path, OWRITE, 0600);
	if(fd < 0 || fprint(fd, "%d\n", pid) < 0)
		sysfatal("record detached writer: %r");
	exits(nil);
}
