/* Inspect provisioned dp9ik keys without displaying or changing them. */
#include <u.h>
#include <libc.h>

void
main(int argc, char **argv)
{
	uchar key[16];
	char *path;
	char status[32];
	int i, j, fd, n, present;

	if(argc < 3)
		sysfatal("usage: auth/checkuser keyfs-mount user ...");
	for(i = 2; i < argc; i++){
		path = smprint("%s/%s/status", argv[1], argv[i]);
		fd = open(path, OREAD);
		free(path);
		if(fd < 0)
			sysfatal("%s needs an enabled, unexpired dp9ik key; provision it with auth/changeuser", argv[i]);
		n = read(fd, status, sizeof status-1);
		close(fd);
		if(n < 0) n = 0;
		status[n] = 0;
		if(strcmp(status, "ok\n") != 0)
			sysfatal("%s needs an enabled, unexpired dp9ik key; provision it with auth/changeuser", argv[i]);
		path = smprint("%s/%s/aeskey", argv[1], argv[i]);
		fd = open(path, OREAD);
		free(path);
		if(fd < 0)
			sysfatal("%s needs an enabled, unexpired dp9ik key; provision it with auth/changeuser", argv[i]);
		memset(key, 0, sizeof key);
		n = readn(fd, key, sizeof key);
		close(fd);
		present = 0;
		for(j = 0; j < sizeof key; j++)
			present |= key[j];
		memset(key, 0, sizeof key);
		if(n != sizeof key || !present)
			sysfatal("%s has no provisioned dp9ik key; use auth/changeuser", argv[i]);
	}
	exits(nil);
}
