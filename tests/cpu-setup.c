#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	char *name, *path, *release;
	uchar magic[8] = {0xcb, 0xee, 0x52, 0x54, 0, 0, 0, 0};
	int fd, i;

	USED(argc);
	name = strrchr(argv[0], '/');
	name = name == nil ? argv[0] : name+1;
	path = smprint("/tmp/%s.pid", name);
	fd = create(path, OWRITE, 0600);
	if(fd < 0)
		sysfatal("record fixture process: %r");
	fprint(fd, "%d\n", getpid());
	close(fd);
	if(strstr(name, "partial") != nil){
		for(i = 0; i < sizeof magic; i++){
			if(write(1, magic+i, 1) != 1)
				exits("disconnected");
			sleep(1000);
		}
	}
	if(strstr(name, "delayed") != nil)
		sleep(6000);
	else if(strstr(name, "retry") == nil || access("/tmp/cpu-setup-ready", AEXIST) < 0){
		sleep(60000);
		exits("stalled");
	}
	release = getenv("nix9");
	if(release == nil)
		sysfatal("Nix release is unavailable");
	argv[0] = smprint("%s/bin/nix-store", release);
	exec(argv[0], argv);
	sysfatal("start serve protocol: %r");
}
