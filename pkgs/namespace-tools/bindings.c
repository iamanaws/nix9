#include <u.h>
#include <libc.h>

typedef struct Old Old;
typedef struct Target Target;
typedef struct Binding Binding;

struct Old {
	char *target, *base, *baseid, *source, *sourceid, *mode, *create, *viewid;
};
struct Target {
	char *path, *base, *view;
	int used, changed;
};
struct Binding {
	char *source, *target, *mode, *anchor;
	int create, required, active;
	Target *view;
};

static Old *old;
static Binding *bindings;
static Target *targets;
static int nold, nbindings, ntargets;
static char **points, **planned, **mounts, **owned;
static int npoints, nplanned, nmounts, nowned;
static int committing, finished;
static void die(char*, ...);

static int
below(char *parent, char *path)
{
	int n;
	n = strlen(parent);
	return strncmp(parent, path, n) == 0 && (path[n] == 0 || path[n] == '/');
}

static void
hashbytes(uvlong *h, char *p, int n)
{
	while(n-- > 0){
		*h ^= (uchar)*p++;
		*h *= 1099511628211ULL;
	}
}

/* Include every entry at the destination, including entries hidden behind the
 * first directory. Directory versions change with ordinary file operations. */
static int
records(char *path, uvlong *hash)
{
	char file[64], buf[8192], copy[8192], *fields[6], *destination;
	int fd, n, nf, count;

	snprint(file, sizeof file, "/proc/%d/ns", getpid());
	fd = open(file, OREAD);
	if(fd < 0)
		die("cannot inspect namespace: %r");
	count = 0;
	while((n = read(fd, buf, sizeof buf - 1)) > 0){
		buf[n] = 0;
		strcpy(copy, buf);
		nf = tokenize(copy, fields, nelem(fields));
		if(nf < 3 || (strcmp(fields[0], "bind") != 0 && strcmp(fields[0], "mount") != 0))
			continue;
		if(fields[1][0] == '-'){
			if(nf < 4)
				die("invalid namespace record");
			destination = fields[3];
		}else
			destination = fields[2];
		if(strcmp(destination, path) == 0){
			count++;
			if(hash != nil)
				hashbytes(hash, buf, n);
		}
	}
	close(fd);
	if(n < 0)
		die("cannot read namespace: %r");
	return count;
}

static int
directory(char *path)
{
	Dir *d;
	int ok;
	d = dirstat(path);
	if(d == nil)
		return 0;
	ok = (d->qid.type & QTDIR) != 0;
	free(d);
	return ok;
}

static char*
identity(char *path)
{
	Dir *d;
	char text[128];
	uvlong hash;

	d = dirstat(path);
	if(d == nil || (d->qid.type & QTDIR) == 0){
		free(d);
		die("directory is unavailable: %s", path);
	}
	hash = 14695981039346656037ULL;
	snprint(text, sizeof text, "%ud:%ud:%llux:%ud", d->type, d->dev, d->qid.path, d->qid.type);
	free(d);
	hashbytes(&hash, text, strlen(text));
	records(path, &hash);
	return smprint("%016llux", hash);
}

static void
same(char *path, char *expected)
{
	char *actual;
	actual = identity(path);
	if(strcmp(actual, expected) != 0)
		die("managed binding was changed: %s", path);
	free(actual);
}

static int
flags(char *mode, int create)
{
	int flag;
	flag = 0;
	if(strcmp(mode, "prepend") == 0)
		flag = MBEFORE;
	else if(strcmp(mode, "append") == 0)
		flag = MAFTER;
	else if(strcmp(mode, "replace") != 0)
		die("invalid binding mode");
	return flag | (create ? MCREATE : 0);
}

static int
known(char *path)
{
	int i;
	for(i = 0; i < nold; i++)
		if(strcmp(old[i].target, path) == 0)
			return 1;
	return 0;
}

static int
firstold(int index)
{
	int i;
	for(i = 0; i < index; i++)
		if(strcmp(old[i].target, old[index].target) == 0)
			return 0;
	return 1;
}

static void
checkold(void)
{
	int i;
	for(i = 0; i < nold; i++){
		same(old[i].source, old[i].sourceid);
		if(firstold(i)){
			same(old[i].base, old[i].baseid);
			same(old[i].target, old[i].viewid);
		}
	}
}

static void
undo(void)
{
	int i;
	if(!committing)
		return;
	for(i = 0; i < ntargets; i++)
		if(targets[i].changed)
			unmount(nil, targets[i].path);
	for(i = 0; i < nold; i++)
		if(firstold(i))
			unmount(nil, old[i].target);
	for(i = 0; i < nold; i++)
		if(bind(old[i].source, old[i].target, flags(old[i].mode, atoi(old[i].create))) < 0)
			fprint(2, "nix9: cannot restore binding %s: %r\n", old[i].target);
	committing = 0;
}

static void
die(char *fmt, ...)
{
	va_list args;
	char *message;
	int i;

	va_start(args, fmt);
	message = vsmprint(fmt, args);
	va_end(args);
	undo();
	for(i = nowned - 1; i >= 0; i--)
		unmount(nil, owned[i]);
	fprint(2, "nix9: namespace binding failed: %s\n", message);
	exits("namespace binding failed");
}

static int
interrupted(void*, char *message)
{
	if(!finished && (strstr(message, "interrupt") != nil || strstr(message, "hangup") != nil || strstr(message, "alarm") != nil))
		die("interrupted");
	return 0;
}

static char*
anchor(void)
{
	char *path;
	path = smprint("/mnt/nix9-bind-%d-%d", getpid(), nowned);
	if(!directory(path) || records(path, nil) != 0)
		die("private binding point is unavailable: %s", path);
	owned = realloc(owned, (nowned + 1) * sizeof *owned);
	if(owned == nil)
		die("out of memory");
	owned[nowned++] = path;
	return path;
}

/* Resolve the original filesystem below a view managed by the old generation. */
static char*
original(char *path)
{
	int i;
	for(i = 0; i < nold; i++)
		if(below(old[i].target, path))
			return smprint("%s%s", old[i].base, path + strlen(old[i].target));
	return strdup(path);
}

static Target*
target(char *path)
{
	int i;
	Target *t;
	for(i = 0; i < ntargets; i++)
		if(strcmp(targets[i].path, path) == 0)
			return &targets[i];
	t = &targets[ntargets++];
	t->path = path;
	return t;
}

static void
checktargets(void)
{
	int i, j, future;
	char *path;
	for(i = 0; i < nbindings; i++){
		if(!known(bindings[i].target) && records(bindings[i].target, nil) != 0)
			die("a manual binding already owns: %s", bindings[i].target);
		path = original(bindings[i].target);
		if(!directory(path)){
			future = 0;
			for(j = 0; j < nplanned; j++)
				if(below(bindings[i].target, planned[j]))
					future = 1;
			if(!future)
				die("binding destination is unavailable: %s", bindings[i].target);
		}
		free(path);
	}
}

static char*
resolve(char *path)
{
	int i, j;
	/* Earlier bindings take precedence over the underlying filesystem. */
	for(i = 0; i < ntargets; i++)
		if(targets[i].used && below(targets[i].path, path))
			return smprint("%s%s", targets[i].view, path + strlen(targets[i].path));
	for(i = 0; i < npoints; i++){
		if(!below(points[i], path))
			continue;
		for(j = 0; j < nmounts; j += 4)
			if(strcmp(mounts[j+1], points[i]) == 0)
				return smprint("%s%s", mounts[j+2], path + strlen(points[i]));
		return nil;
	}
	return original(path);
}

static void
stage(void)
{
	Binding *b;
	Target *t;
	char *path;
	int i, j;

	for(i = 0; i < nbindings; i++){
		b = &bindings[i];
		t = target(b->target);
		b->view = t;
		if(t->base == nil){
			for(j = 0; j < nold; j++)
				if(strcmp(old[j].target, t->path) == 0)
					t->base = old[j].base;
			if(t->base == nil){
				t->base = anchor();
				path = original(t->path);
				if(bind(path, t->base, MREPL) < 0)
					die("cannot retain original directory %s: %r", t->path);
				free(path);
			}
			t->view = anchor();
			if(bind(t->base, t->view, MREPL) < 0)
				die("cannot stage destination %s: %r", t->path);
		}
		path = resolve(b->source);
		if(path == nil || !directory(path)){
			free(path);
			if(b->required)
				die("required binding source is unavailable: %s", b->source);
			fprint(2, "nix9: optional binding source is unavailable: %s\n", b->source);
			continue;
		}
		b->anchor = anchor();
		if(bind(path, b->anchor, b->create ? MCREATE : MREPL) < 0)
			die("cannot retain binding source %s: %r", b->source);
		free(path);
		if(bind(b->anchor, t->view, flags(b->mode, b->create)) < 0)
			die("cannot stage binding at %s: %r", b->target);
		t->used = b->active = 1;
	}
}

static void
commit(void)
{
	int i;
	/* Copying a staged union in one bind drops MCREATE on its tail entries.
	 * Replay each source so creation flags and rollback preserve native order. */
	committing = 1;
	for(i = 0; i < nold; i++)
		if(firstold(i) && unmount(nil, old[i].target) < 0)
			die("cannot remove old binding %s: %r", old[i].target);
	for(i = 0; i < nbindings; i++){
		if(!bindings[i].active)
			continue;
		if(bind(bindings[i].anchor, bindings[i].target, flags(bindings[i].mode, bindings[i].create)) < 0)
			die("cannot install binding %s: %r", bindings[i].target);
		bindings[i].view->changed = 1;
	}
}

static int
retained(char *path)
{
	int i;
	for(i = 0; i < nbindings; i++)
		if(bindings[i].active && (strcmp(path, bindings[i].anchor) == 0 || strcmp(path, bindings[i].view->base) == 0))
			return 1;
	return 0;
}

static int
count(char ***args, int *remaining)
{
	char *end;
	long n;
	if(*remaining == 0)
		die("incomplete binding request");
	n = strtol(**args, &end, 10);
	(*args)++;
	(*remaining)--;
	if(*end != 0 || n < 0 || n > *remaining)
		die("invalid binding request length");
	return n;
}

void
main(int argc, char **argv)
{
	int i, words;
	char *action, *baseid, *sourceid, *viewid;

	if(argc < 3)
		die("usage: nix9-bindings {check|apply|detach} OLDCOUNT OLD... [POINTCOUNT POINTS... PLANCOUNT DIRS... MOUNTCOUNT MOUNTS... SOURCE TARGET MODE CREATE REQUIRED ...]");
	action = argv[1];
	argv += 2;
	argc -= 2;
	words = count(&argv, &argc);
	if(words % 8 != 0)
		die("invalid inherited binding state");
	nold = words / 8;
	old = mallocz(nold * sizeof *old, 1);
	for(i = 0; i < nold; i++){
		old[i].target = argv[0]; old[i].base = argv[1]; old[i].baseid = argv[2];
		old[i].source = argv[3]; old[i].sourceid = argv[4]; old[i].mode = argv[5];
		old[i].create = argv[6]; old[i].viewid = argv[7];
		if(strncmp(old[i].base, "/mnt/nix9-bind-", 15) != 0 || strncmp(old[i].source, "/mnt/nix9-bind-", 15) != 0)
			die("invalid inherited binding anchors");
		flags(old[i].mode, atoi(old[i].create));
		argv += 8;
		argc -= 8;
	}
	checkold();
	if(strcmp(action, "detach") == 0){
		if(argc != 0)
			die("unexpected detach arguments");
		for(i = 0; i < nold; i++)
			if(firstold(i) && unmount(nil, old[i].target) < 0)
				die("cannot detach binding %s: %r", old[i].target);
		exits(nil);
	}
	npoints = count(&argv, &argc); points = argv; argv += npoints; argc -= npoints;
	nplanned = count(&argv, &argc); planned = argv; argv += nplanned; argc -= nplanned;
	nmounts = count(&argv, &argc); mounts = argv; argv += nmounts; argc -= nmounts;
	if(nmounts % 4 != 0 || argc % 5 != 0)
		die("invalid binding request");
	nbindings = argc / 5;
	bindings = mallocz(nbindings * sizeof *bindings, 1);
	targets = mallocz(nbindings * sizeof *targets, 1);
	for(i = 0; i < nbindings; i++){
		bindings[i].source = argv[0]; bindings[i].target = argv[1]; bindings[i].mode = argv[2];
		bindings[i].create = atoi(argv[3]); bindings[i].required = atoi(argv[4]);
		flags(bindings[i].mode, bindings[i].create);
		argv += 5;
	}
	checktargets();
	if(strcmp(action, "check") == 0)
		exits(nil);
	if(strcmp(action, "apply") != 0)
		die("invalid binding action");
	atnotify(interrupted, 1);
	stage();
	commit();
	/* Retain undo anchors until all identities have been read successfully. */
	print("nix9-bindings-ready");
	for(i = 0; i < nbindings; i++){
		if(!bindings[i].active)
			continue;
		baseid = identity(bindings[i].view->base);
		sourceid = identity(bindings[i].anchor);
		viewid = identity(bindings[i].target);
		print(" %s %s %s %s %s %s %d %s", bindings[i].target, bindings[i].view->base, baseid,
			bindings[i].anchor, sourceid, bindings[i].mode, bindings[i].create, viewid);
	}
	finished = 1;
	committing = 0;
	print("\n");
	for(i = 0; i < nold; i++){
		if(!retained(old[i].source)) unmount(nil, old[i].source);
		if(firstold(i) && !retained(old[i].base)) unmount(nil, old[i].base);
	}
	for(i = nowned - 1; i >= 0; i--)
		if(!retained(owned[i])) unmount(nil, owned[i]);
	exits(nil);
}
