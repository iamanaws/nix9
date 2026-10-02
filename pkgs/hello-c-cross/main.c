#include <u.h>
#include <libc.h>

void
main(void)
{
	char buf[64];
	char *path = "/tmp/nix9-file-probe";
	char *payload = "nix9-file-roundtrip";
	int fd, n, p[2], pid;
	Waitmsg *w;

	fd = create(path, ORDWR|ORCLOSE, 0600);
	if(fd < 0)
		sysfatal("create: %r");
	n = strlen(payload);
	if(write(fd, payload, n) != n || seek(fd, 0, 0) != 0)
		sysfatal("write/seek: %r");
	if(readn(fd, buf, n) != n || memcmp(buf, payload, n) != 0)
		sysfatal("file contents differ");
	close(fd);
	if(access(path, AEXIST) == 0)
		sysfatal("ORCLOSE did not remove the file");
	print("PASS: C file create/write/seek/read/remove\n");

	if(pipe(p) < 0)
		sysfatal("pipe: %r");
	pid = fork();
	if(pid < 0)
		sysfatal("fork: %r");
	if(pid == 0){
		close(p[0]);
		if(dup(p[1], 1) < 0)
			sysfatal("dup: %r");
		close(p[1]);
		execl("/bin/echo", "echo", "nix9-child", nil);
		sysfatal("exec: %r");
	}
	close(p[1]);
	n = readn(p[0], buf, sizeof(buf));
	close(p[0]);
	w = wait();
	if(w == nil || w->pid != pid || w->msg[0] != 0)
		sysfatal("child failed");
	free(w);
	if(n != strlen("nix9-child\n") || memcmp(buf, "nix9-child\n", n) != 0)
		sysfatal("unexpected child output");
	print("PASS: C pipe/fork/exec/wait\n");
	print("Hello from Nix-built C on 9front/amd64!\n");
	exits(nil);
}
