#include <u.h>
#include <libc.h>

/* Hold note-group descriptors before exec so cleanup never follows a reused PID. */
static int plumber = -1, rio = -1;
static int interrupted;

static void
cleanup(void)
{
	if(rio >= 0){
		write(rio, "hangup", 6);
		close(rio);
		rio = -1;
	}
	if(plumber >= 0){
		write(plumber, "kill", 4);
		close(plumber);
		plumber = -1;
	}
}

static void
note(void *v, char *message)
{
	USED(v);
	if(strcmp(message, "interrupt") == 0 || strcmp(message, "hangup") == 0){
		interrupted = 1;
		if(rio >= 0)
			write(rio, "hangup", 6);
		noted(NCONT);
	}
	cleanup();
	noted(NDFLT);
}

static int
spawn(char **args, int *group)
{
	int sync[2], pid;
	char path[64], byte;

	if(pipe(sync) < 0)
		sysfatal("startup pipe: %r");
	pid = rfork(RFPROC|RFFDG|RFNOTEG);
	if(pid < 0)
		sysfatal("rfork: %r");
	if(pid == 0){
		close(sync[1]);
		if(read(sync[0], &byte, 1) != 1)
			exits("startup cancelled");
		close(sync[0]);
		exec(args[0], args);
		sysfatal("exec %s: %r", args[0]);
	}
	close(sync[0]);
	snprint(path, sizeof path, "/proc/%d/notepg", pid);
	*group = open(path, OWRITE|OCEXEC);
	if(*group < 0)
		sysfatal("open %s: %r", path);
	if(write(sync[1], "1", 1) != 1)
		sysfatal("start %s: %r", args[0]);
	close(sync[1]);
	return pid;
}

static void
waitfor(int pid, int window)
{
	Waitmsg *w;
	char error[ERRMAX];

	for(;;){
		w = wait();
		if(w == nil){
			rerrstr(error, sizeof error);
			if(strcmp(error, "interrupted") == 0)
				continue;
			sysfatal("wait: %s", error);
		}
		if(w->pid != pid){
			free(w);
			continue;
		}
		if(w->msg[0] && !window)
			sysfatal("plumber: %s", w->msg);
		if(w->msg[0] && !interrupted && strcmp(w->msg, "hangup") != 0)
			sysfatal("rio: %s", w->msg);
		free(w);
		return;
	}
}

void
main(int argc, char **argv)
{
	char service[64];
	char *args[7];
	int pid;

	if(argc < 5)
		sysfatal("usage: nix9-session-run plumber rules rio args...");
	atexit(cleanup);
	notify(note);
	snprint(service, sizeof service, "nix9-plumb.%s.%d", getuser(), getpid());
	args[0] = argv[1];
	args[1] = "-p";
	args[2] = argv[2];
	args[3] = "-s";
	args[4] = service;
	args[5] = nil;
	pid = spawn(args, &plumber);
	waitfor(pid, 0);
	if(interrupted)
		exits("interrupted");
	pid = spawn(argv+3, &rio);
	waitfor(pid, 1);
	close(rio);
	rio = -1;
	exits(nil);
}
