#include <u.h>
#include <libc.h>

typedef struct Setting Setting;
struct Setting {
	char *path;
	ulong mode;
	char *owner;
	char *group;
};

static Setting *settings;
static int nsettings;
static void prepare(Setting*);

static void
usage(void)
{
	fprint(2, "usage: nix9-directories {check|prepare} path mode owner group ...\n");
	exits("usage");
}

static void
regular(char *path, Dir *d)
{
	if(d->qid.type != QTDIR || (d->mode & (DMDIR|DMAPPEND|DMEXCL|DMTMP|DMAUTH)) != DMDIR)
		sysfatal("not a regular directory: %s", path);
}

static char*
parent(char *path)
{
	char *p, *end;

	p = strdup(path);
	if(p == nil)
		sysfatal("out of memory");
	end = strrchr(p, '/');
	if(end == p)
		end++;
	*end = 0;
	return p;
}

static void
check(char *path)
{
	Dir *d;
	char *p;

	d = dirstat(path);
	if(d != nil){
		regular(path, d);
		free(d);
		return;
	}
	if(strcmp(path, "/") == 0)
		sysfatal("cannot inspect filesystem root: %r");
	p = parent(path);
	check(p);
	free(p);
}

static void
ensure(char *path)
{
	Dir *d;
	char *p;
	ulong mode;
	int fd, i;
	Setting implicit;

	d = dirstat(path);
	if(d != nil){
		regular(path, d);
		free(d);
		return;
	}
	p = parent(path);
	ensure(p);
	free(p);
	/* Declared directories stay private until all paths have been created. */
	mode = 0755;
	for(i = 0; i < nsettings; i++)
		if(strcmp(settings[i].path, path) == 0){
			mode = 0700;
			break;
		}
	fd = create(path, OREAD|OEXCL|OCEXEC, DMDIR|mode);
	if(fd >= 0)
		close(fd);
	d = dirstat(path);
	if(d == nil)
		sysfatal("cannot create directory %s: %r", path);
	regular(path, d);
	free(d);
	/* 9P create may mask permission bits with the parent's current mode. */
	if(fd >= 0 && mode == 0755){
		memset(&implicit, 0, sizeof implicit);
		implicit.path = path;
		implicit.mode = 0755;
		prepare(&implicit);
	}
}

static int
matches(Setting *s, Dir *d)
{
	return (d->mode & 0777) == s->mode &&
		(s->owner == nil || strcmp(s->owner, d->uid) == 0) &&
		(s->group == nil || strcmp(s->group, d->gid) == 0);
}

static void
prepare(Setting *s)
{
	Dir *d, change;

	d = dirstat(s->path);
	if(d == nil)
		sysfatal("cannot inspect directory %s: %r", s->path);
	regular(s->path, d);
	if(matches(s, d)){
		free(d);
		return;
	}
	nulldir(&change);
	if((d->mode & 0777) != s->mode)
		change.mode = DMDIR|s->mode;
	if(s->owner != nil && strcmp(s->owner, d->uid) != 0)
		change.uid = s->owner;
	if(s->group != nil && strcmp(s->group, d->gid) != 0)
		change.gid = s->group;
	free(d);
	if(dirwstat(s->path, &change) < 0)
		sysfatal("cannot set directory metadata on %s: %r", s->path);
	d = dirstat(s->path);
	if(d == nil || !matches(s, d))
		sysfatal("directory metadata was not applied: %s", s->path);
	free(d);
}

void
main(int argc, char **argv)
{
	Setting *s;
	char *end;
	int i, apply;

	if(argc < 6 || (argc-2)%4 != 0)
		usage();
	apply = strcmp(argv[1], "prepare") == 0;
	if(!apply && strcmp(argv[1], "check") != 0)
		usage();
	nsettings = (argc-2)/4;
	settings = mallocz(nsettings*sizeof(Setting), 1);
	if(settings == nil)
		sysfatal("out of memory");
	for(i = 0; i < nsettings; i++){
		s = &settings[i];
		s->path = argv[2+4*i];
		if(s->path[0] != '/' || s->path[1] == 0)
			usage();
		s->mode = strtoul(argv[3+4*i], &end, 8);
		if(strlen(argv[3+4*i]) != 4 || argv[3+4*i][0] != '0' || *end || s->mode > 0777)
			usage();
		s->owner = strcmp(argv[4+4*i], "-") == 0 ? nil : argv[4+4*i];
		s->group = strcmp(argv[5+4*i], "-") == 0 ? nil : argv[5+4*i];
	}
	/* Inspect every path before creating anything or changing metadata. */
	for(i = 0; i < nsettings; i++)
		check(settings[i].path);
	if(apply){
		for(i = 0; i < nsettings; i++)
			ensure(settings[i].path);
		/* Children precede parents that may restrict traversal or change owner. */
		for(i = nsettings-1; i >= 0; i--)
			prepare(&settings[i]);
	}
	exits(nil);
}
