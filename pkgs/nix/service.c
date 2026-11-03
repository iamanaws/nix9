/* Native authentication, TLS and identity changes for Nix's worker protocol. */
#include <u.h>
#include <libc.h>
#include <bio.h>
#include <auth.h>
#include <mp.h>
#include <libsec.h>

static char *address = "tcp!127.0.0.1!17051";
static char *keys = "";
static char *policy, *worker, *launcher;
static char *builduser = "none";
static char *clientpid;
static int connectionctl = -1;

static void
closeclient(void)
{
	if(connectionctl >= 0)
		fprint(connectionctl, "close");
}

static void
closeconnection(void)
{
	if(connectionctl >= 0)
		hangup(connectionctl);
}

typedef struct Input Input;
struct Input {
	char *name, *data;
	long size;
};

static void
usage(void)
{
	fprint(2, "usage: nix-store-service -c [-a address] [-k keypattern] [-p client-pid]\n"
		"       nix-store-service [-a address] [-k keypattern] -u allowed-users -w worker\n");
	exits("usage");
}

static int
username(char *s)
{
	int n;

	if(s == nil || (n = strlen(s)) == 0 || n >= 28)
		return 0;
	if(!(*s >= 'a' && *s <= 'z') && !(*s >= 'A' && *s <= 'Z') && !(*s >= '0' && *s <= '9'))
		return 0;
	for(; *s; s++)
		if(!(*s >= 'a' && *s <= 'z') && !(*s >= 'A' && *s <= 'Z') &&
		   !(*s >= '0' && *s <= '9') && *s != '_' && *s != '-' && *s != '.')
			return 0;
	return 1;
}

static void
closeexcept(int keep, int other)
{
	Dir *dirs;
	int fd, i, n, value;

	fd = open("/fd", OREAD);
	if(fd < 0)
		sysfatal("open /fd: %r");
	n = dirreadall(fd, &dirs);
	close(fd);
	if(n < 0)
		sysfatal("read /fd: %r");
	for(i = 0; i < n; i++){
		value = atoi(dirs[i].name);
		if(value > 2 && value != keep && value != other)
			close(value);
	}
	free(dirs);
}

static void
closeextraexcept(int keep)
{
	closeexcept(keep, -1);
}

static void
closeextra(void)
{
	closeextraexcept(-1);
}

static void
standardfds(void)
{
	int i, fd;

	/* A caller may have closed stdin. Reserve all three standard slots before
	 * opening capabilities that must survive replacing the builder's stdio. */
	for(i = 0; i < 3; i++){
		fd = dup(i, -1);
		if(fd >= 0){
			close(fd);
			continue;
		}
		fd = open("/dev/null", ORDWR);
		if(fd < 0 || dup(fd, i) < 0)
			sysfatal("reserve standard descriptor: %r");
		if(fd != i)
			close(fd);
	}
}

static int
allowed(char *user)
{
	Biobuf *b;
	Dir *d;
	char *line, *words[64];
	int i, n, ok;

	b = Bopen(policy, OREAD);
	if(b == nil)
		return 0;
	d = dirfstat(Bfildes(b));
	if(d == nil || (d->mode & DMDIR) || strcmp(d->uid, getuser()) != 0 || (d->mode & 022) != 0){
		free(d);
		Bterm(b);
		return 0;
	}
	free(d);
	ok = 0;
	while(line = Brdstr(b, '\n', 1)){
		char *comment;
		if(comment = strchr(line, '#'))
			*comment = 0;
		n = tokenize(line, words, nelem(words));
		for(i = 0; i < n; i++)
			if(strcmp(words[i], user) == 0 || strcmp(words[i], "*") == 0)
				ok = 1;
		free(line);
	}
	Bterm(b);
	return ok;
}

static void
transfer(int from, int to)
{
	char buf[IOUNIT];
	int n, sent, count;

	while((n = read(from, buf, sizeof buf)) > 0)
		for(sent = 0; sent < n; sent += count){
			count = write(to, buf + sent, n - sent);
			if(count <= 0)
				return;
		}
}

static void
writeall(int fd, char *data, long size)
{
	long n;

	while(size > 0){
		n = write(fd, data, size);
		if(n <= 0)
			sysfatal("write build input: %r");
		data += n;
		size -= n;
	}
}

static void
watchclient(int ctl)
{
	char *path, *end, byte;
	long pid;
	int fd, owner;

	if(clientpid == nil)
		return;
	pid = strtol(clientpid, &end, 10);
	if(*end != 0 || pid <= 1)
		sysfatal("invalid client pid");
	path = smprint("/proc/%ld/status", pid);
	fd = open(path, OREAD|OCEXEC);
	free(path);
	if(fd < 0)
		sysfatal("open client process: %r");
	path = smprint("/proc/%d/status", getpid());
	owner = open(path, OREAD|OCEXEC);
	free(path);
	if(owner < 0)
		sysfatal("open connection process: %r");
	switch(rfork(RFPROC|RFFDG|RFNOWAIT)){
	case -1:
		sysfatal("fork client monitor: %r");
	case 0:
		/* Orphaned cc9 threads may retain pipe descriptors after their main
		 * process dies. Keep only the TCP control and process descriptors so we
		 * can close the connection before killing helpers, without retaining pipes. */
		dup(ctl, 0);
		closeexcept(fd, owner);
		close(1);
		close(2);
		while(pread(fd, &byte, 1, 0) == 1 && pread(owner, &byte, 1, 0) == 1)
			sleep(100);
		fprint(0, "close");
		postnote(PNGROUP, getpid(), "kill");
		exits(nil);
	default:
		close(fd);
		close(owner);
	}
}

static int
clientnote(void*, char *note)
{
	/* Let transfer() finish and stop both directions on a broken pipe. */
	return strstr(note, "sys: write on closed pipe") != nil;
}

static void
client(void)
{
	AuthInfo *ai;
	TLSconn conn;
	int fd, ctl;

	if(rfork(RFNOTEG) < 0)
		sysfatal("client note group: %r");
	atnotify(clientnote, 1);
	/* Bound connection setup before the process watcher can take over. */
	alarm(30000);
	fd = dial(address, nil, nil, &ctl);
	if(fd < 0)
		sysfatal("dial store service: %r");
	connectionctl = ctl;
	atexit(closeclient);
	watchclient(ctl);
	ai = auth_proxy(fd, nil, "proto=p9any role=client %s", keys);
	if(ai == nil)
		sysfatal("store authentication: %r");
	memset(&conn, 0, sizeof conn);
	conn.pskID = "p9secret";
	conn.psk = ai->secret;
	conn.psklen = ai->nsecret;
	fd = tlsClient(fd, &conn);
	auth_freeAI(ai);
	if(fd < 0)
		sysfatal("store TLS: %r");
	alarm(0);
	switch(rfork(RFPROC|RFFDG|RFNOWAIT)){
	case -1:
		sysfatal("fork transfer: %r");
	case 0:
		transfer(0, fd);
		/* Wake the peer even when loopback TCP bypasses the packet path. */
		fprint(ctl, "close");
		break;
	default:
		transfer(fd, 1);
		break;
	}
	hangup(ctl);
	/* Stop both transfer directions and the watcher in our private group. */
	postnote(PNGROUP, getpid(), "kill");
	exits(nil);
}

static void
connection(int ctl)
{
	AuthInfo *ai;
	TLSconn conn;
	char *args[2], *dump;
	Waitmsg *w;
	int fd, pid, exited;

	alarm(30000);
	ai = auth_proxy(0, nil, "proto=p9any role=server %s", keys);
	if(ai == nil)
		sysfatal("store authentication: %r");
	if(!username(ai->cuid) || strcmp(ai->cuid, builduser) == 0 || !allowed(ai->cuid))
		sysfatal("store access denied");
	memset(&conn, 0, sizeof conn);
	conn.pskID = "p9secret";
	conn.psk = ai->secret;
	conn.psklen = ai->nsecret;
	fd = tlsServer(0, &conn);
	if(fd < 0)
		sysfatal("store TLS: %r");
	alarm(0);
	connectionctl = ctl;
	atexit(closeconnection);
	/* Keep the TCP control until the worker exits, then explicitly hang up.
	 * Closing a spliced loopback conversation without hangup can close its
	 * former peer after that slot has been reused by another connection. */
	switch(pid = rfork(RFPROC|RFFDG)){
	case -1:
		sysfatal("fork daemon worker: %r");
	case 0:
		close(ctl);
		connectionctl = -1;
		break;
	default:
		closeexcept(ctl, -1);
		close(0);
		close(1);
		for(;;){
			w = wait();
			if(w == nil)
				sysfatal("wait for daemon worker: %r");
			exited = w->pid;
			free(w);
			if(exited == pid)
				exits(nil);
		}
	}
	putenv("NIX9_CLIENT_USER", ai->cuid);
	putenv("NIX9_BUILD_USER", builduser);
	putenv("NIX9_BUILD_LAUNCHER", launcher);
	dump = smprint("%.*s/nix-store", (int)(strrchr(worker, '/') - worker), worker);
	putenv("NIX9_DUMP_PROGRAM", dump);
	putenv("NIX9_RAMFS", smprint("%.*s/../libexec/nix-ramfs", (int)(strrchr(worker, '/') - worker), worker));
	putenv("NIX_REMOTE", "local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log");
	auth_freeAI(ai);
	dup(fd, 0);
	dup(fd, 1);
	closeextra();
	args[0] = worker;
	args[1] = nil;
	exec(worker, args);
	sysfatal("exec daemon worker: %r");
}

static char*
jobservice(char *stage)
{
	char *copy, *name, *p, *result;

	p = strrchr(stage, '/');
	if(p == nil || p == stage || strcmp(p, "/view") != 0)
		sysfatal("invalid build job path");
	copy = strdup(stage);
	*strrchr(copy, '/') = 0;
	name = strrchr(copy, '/');
	if(name == nil || strncmp(++name, "build-", 6) != 0)
		sysfatal("invalid build job name");
	for(p = name; *p; p++)
		if((*p < 'a' || *p > 'z') && (*p < '0' || *p > '9') && *p != '-')
			sysfatal("invalid build job name");
	result = smprint("#s/nix9-%s", name);
	free(copy);
	return result;
}

static void
prepare(char *stage, char *program)
{
	char *service, *pidfile;
	int p[2], pid, fd, record;

	service = jobservice(stage);
	pidfile = smprint("%s/ramfs.pid", stage);
	record = create(pidfile, OWRITE, 0600);
	if(record < 0 || pipe(p) < 0)
		sysfatal("prepare private build filesystem: %r");
	fd = create(service, OWRITE, 0600);
	if(fd < 0)
		sysfatal("post private build filesystem: %r");
	pid = rfork(RFPROC|RFNOWAIT|RFNAMEG|RFENVG|RFFDG);
	if(pid < 0)
		sysfatal("fork private build filesystem: %r");
	if(pid == 0){
		dup(p[0], 0);
		dup(p[0], 1);
		closeextra();
		execl(program, program, "-i", "-p", nil);
		sysfatal("exec private build filesystem: %r");
	}
	if(fprint(record, "%d\n", pid) < 0 || fprint(fd, "%d", p[1]) < 0){
		remove(service);
		postnote(PNPROC, pid, "kill");
		sysfatal("record private build filesystem: %r");
	}
	close(record);
	close(fd);
	close(p[0]);
	close(p[1]);
	free(service);
	free(pidfile);
}

static void
revoke(char *stage)
{
	char *service, *pidfile, buf[32], *path;
	Dir *d;
	int fd, n, pid, i;

	service = jobservice(stage);
	d = dirstat(service);
	if(d != nil){
		if(strcmp(d->uid, getuser()) != 0)
			sysfatal("private build filesystem has a different owner");
		free(d);
		if(remove(service) < 0)
			sysfatal("unpost private build filesystem: %r");
	}
	pidfile = smprint("%s/ramfs.pid", stage);
	fd = open(pidfile, OREAD);
	if(fd < 0)
		return;
	n = read(fd, buf, sizeof buf-1);
	close(fd);
	if(n <= 0)
		sysfatal("invalid private filesystem process");
	buf[n] = 0;
	pid = atoi(buf);
	if(pid <= 1)
		sysfatal("invalid private filesystem process");
	path = smprint("/proc/%d/ctl", pid);
	d = dirstat(path);
	if(d == nil)
		return;
	if(strcmp(d->uid, getuser()) != 0)
		sysfatal("private filesystem process has a different owner");
	free(d);
	postnote(PNPROC, pid, "kill");
	for(i = 0; i < 100; i++){
		d = dirstat(path);
		if(d == nil)
			return;
		free(d);
		sleep(10);
	}
	sysfatal("private filesystem process did not stop");
}

static void
build(int argc, char **argv)
{
	char *mode, *user, *stage, *store, *path, *service;
	Dir *files;
	Input *inputs;
	int fd, storage, i, n;

	if(argc < 4 || (strcmp(argv[0], "-R") != 0 && argc < 5))
		usage();
	mode = argv[0];
	user = argv[1];
	stage = argv[2];
	store = argv[3];
	if(strcmp(user, "none") != 0 || strcmp(user, getuser()) == 0 || store[0] != '/')
		sysfatal("shared builds require the anonymous native identity");
	if(strcmp(mode, "-R") == 0){
		revoke(stage);
		exits(nil);
	}
	if(rfork(RFNAMEG|RFENVG|RFFDG) < 0)
		sysfatal("private build groups: %r");
	if(strcmp(mode, "-B") != 0 && rfork(RFNOTEG) < 0)
		sysfatal("private output-reader note group: %r");
	service = jobservice(stage);
	storage = open(service, ORDWR|OCEXEC);
	if(storage < 0)
		sysfatal("open private build filesystem: %r");
	if(strcmp(mode, "-D") == 0){
		path = smprint("%s/output.nar", stage);
		fd = create(path, OWRITE, 0600);
		if(fd < 0 || dup(fd, 1) < 0)
			sysfatal("open private output archive: %r");
		close(fd);
		free(path);
	}
	/* Copy only derivation-provided passAsFile inputs before dropping identity. */
	inputs = nil;
	n = 0;
	if(strcmp(mode, "-B") == 0){
		path = smprint("%s/build", stage);
		fd = open(path, OREAD);
		if(fd < 0)
			sysfatal("open build inputs: %r");
		n = dirreadall(fd, &files);
		close(fd);
		if(n < 0)
			sysfatal("read build inputs: %r");
		inputs = mallocz(n * sizeof(Input), 1);
		if(n != 0 && inputs == nil)
			sysfatal("out of memory reading build inputs");
		for(i = 0; i < n; i++){
			if((files[i].mode & DMDIR) || files[i].length > 0x7fffffff)
				sysfatal("invalid build input");
			inputs[i].name = strdup(files[i].name);
			inputs[i].size = files[i].length;
			inputs[i].data = malloc(inputs[i].size + 1);
			if(inputs[i].data == nil)
				sysfatal("out of memory reading build input");
			path = smprint("%s/build/%s", stage, inputs[i].name);
			fd = open(path, OREAD);
			if(fd < 0 || readn(fd, inputs[i].data, inputs[i].size) != inputs[i].size)
				sysfatal("read build input: %r");
			close(fd);
			free(path);
		}
		free(files);
	}
	unmount(nil, "/mnt/factotum");
	unmount(nil, "/mnt");
	fd = open("/dev/null", OREAD);
	if(fd < 0 || dup(fd, 0) < 0)
		sysfatal("clear builder input: %r");
	if(fd != storage && fd > 2)
		close(fd);
	closeextraexcept(storage);
	if(procsetuser(user) < 0)
		sysfatal("build identity: %r");
	/* Reattach the machine filesystem anonymously. Private RAMFS is the only
	 * writable authority carried from the service, and is revoked after import. */
	putenv("cputype", "amd64");
	putenv("rootdir", "/root");
	if(newns(user, nil) < 0)
		sysfatal("builder namespace: %r");
	unmount(nil, "/mnt/factotum");
	if(mount(storage, -1, "/tmp", MREPL|MCREATE, "") < 0)
		sysfatal("mount private build filesystem: %r");
	closeextra();
	if(strcmp(mode, "-B") == 0){
		fd = create("/tmp/store", OREAD, DMDIR|0700);
		if(fd < 0)
			sysfatal("create private build store: %r");
		close(fd);
		fd = create("/tmp/build", OREAD, DMDIR|0700);
		if(fd < 0)
			sysfatal("create private build directory: %r");
		close(fd);
		for(i = 0; i < n; i++){
			path = smprint("/tmp/build/%s", inputs[i].name);
			fd = create(path, OWRITE, 0444);
			if(fd < 0)
				sysfatal("write build input: %r");
			writeall(fd, inputs[i].data, inputs[i].size);
			close(fd);
			free(path);
			free(inputs[i].name);
			free(inputs[i].data);
		}
		free(inputs);
	}
	if(bind("/tmp/store", store, MBEFORE|MCREATE) < 0)
		sysfatal("build store namespace: %r");
	putenv("home", "/homeless-shelter");
	fd = open("/mnt/factotum/ctl", OWRITE);
	if(fd >= 0)
		sysfatal("builder still has a factotum");
	if(chdir("/tmp/build") < 0)
		sysfatal("build directory: %r");
	exec(argv[4], argv+4);
	sysfatal("exec builder: %r");
}

void
main(int argc, char **argv)
{
	char dir[NETPATHLEN], accepted[NETPATHLEN];
	int dialfd, ctl, fd, isclient;

	launcher = strdup(argv[0]);
	fmtinstall('[', encodefmt);
	fmtinstall('H', encodefmt);
	standardfds();
	if(argc == 4 && strcmp(argv[1], "-P") == 0){
		prepare(argv[2], argv[3]);
		exits(nil);
	}
	if(argc > 1 && (strcmp(argv[1], "-B") == 0 || strcmp(argv[1], "-D") == 0 || strcmp(argv[1], "-R") == 0))
		build(argc-1, argv+1);
	isclient = 0;
	ARGBEGIN{
	case 'c': isclient = 1; break;
	case 'p': clientpid = EARGF(usage()); break;
	case 'a': address = EARGF(usage()); break;
	case 'k': keys = EARGF(usage()); break;
	case 'u': policy = EARGF(usage()); break;
	case 'w': worker = EARGF(usage()); break;
	default: usage();
	}ARGEND
	if(argc != 0)
		usage();
	if(strchr(keys, '!') != nil || strchr(keys, '\n') != nil || strchr(keys, '\r') != nil)
		sysfatal("key pattern must contain public factotum attributes only");
	if(isclient)
		client();
	if(policy == nil || worker == nil || worker[0] != '/' || strrchr(worker, '/') == nil ||
	   launcher[0] != '/' || !username(builduser) || strcmp(builduser, getuser()) == 0)
		usage();
	if(rfork(RFNAMEG|RFENVG|RFFDG|RFNOTEG) < 0)
		sysfatal("service groups: %r");
	dialfd = announce(address, dir);
	if(dialfd < 0)
		sysfatal("announce store service: %r");
	for(;;){
		ctl = listen(dir, accepted);
		if(ctl < 0)
			sysfatal("listen store service: %r");
		switch(rfork(RFPROC|RFNOWAIT|RFNAMEG|RFENVG|RFFDG)){
		case -1:
			close(ctl);
			break;
		case 0:
			close(dialfd);
			fd = accept(ctl, accepted);
			if(fd < 0)
				sysfatal("accept store client: %r");
			dup(fd, 0);
			dup(fd, 1);
			closeextraexcept(ctl);
			connection(ctl);
		default:
			close(ctl);
		}
	}
}
