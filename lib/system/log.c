#include <u.h>
#include <libc.h>
#include <ctype.h>

static void
usage(void)
{
	fprint(2, "usage: nix9-log {check|prepare} name mode ... | event {boot|switch|rollback} system\n");
	exits("usage");
}

static void
regular(char *path, Dir *d)
{
	if((d->qid.type & ~QTAPPEND) != 0 || (d->mode & (DMDIR|DMEXCL|DMTMP|DMAUTH)) != 0)
		sysfatal("not a regular log file: %s", path);
}

static char*
logpath(char *name)
{
	char *p;

	if(strlen(name) == 0 || strlen(name) > 64 || !isalnum(name[0]))
		sysfatal("invalid log name: %s", name);
	for(p = name; *p; p++)
		if(!isalnum(*p) && *p != '.' && *p != '_' && *p != '-')
			sysfatal("invalid log name: %s", name);
	return smprint("/sys/log/%s", name);
}

static ulong
logmode(char *text)
{
	char *end;
	ulong mode;

	mode = strtoul(text, &end, 8);
	if(strlen(text) != 4 || text[0] != '0' || *end || mode > 0777 || (mode & 0200) == 0)
		sysfatal("invalid log mode: %s", text);
	return mode | DMAPPEND;
}

static void
prepare(char *path, ulong mode)
{
	Dir *d, change;
	int fd;

	d = dirstat(path);
	if(d == nil){
		/* Exclusive creation cannot truncate a file created after our stat. */
		fd = create(path, OWRITE|OEXCL|OCEXEC, mode);
		if(fd >= 0)
			close(fd);
		d = dirstat(path);
		if(d == nil)
			sysfatal("cannot create log file %s: %r", path);
	}
	regular(path, d);
	if(d->mode != mode){
		nulldir(&change);
		change.mode = mode;
		if(dirwstat(path, &change) < 0)
			sysfatal("cannot set log mode on %s: %r", path);
	}
	free(d);
	fd = open(path, OWRITE|OCEXEC);
	if(fd < 0)
		sysfatal("cannot write log file %s: %r", path);
	d = dirfstat(fd);
	if(d == nil)
		sysfatal("cannot stat log file %s: %r", path);
	regular(path, d);
	if(d->mode != mode)
		sysfatal("log mode was not applied on %s", path);
	free(d);
	close(fd);
}

static void
event(char *action, char *system)
{
	char host[128], *line;
	Dir *d;
	int fd, n, length;

	if(strcmp(action, "boot") != 0 && strcmp(action, "switch") != 0 && strcmp(action, "rollback") != 0)
		usage();
	if(strncmp(system, "/usr/local/nix/store/", 21) != 0 || strchr(system, '\n') || strchr(system, '\r'))
		sysfatal("invalid system path");
	fd = open("/dev/sysname", OREAD|OCEXEC);
	if(fd < 0)
		sysfatal("cannot open system name: %r");
	n = read(fd, host, sizeof(host)-1);
	if(n <= 0)
		sysfatal("cannot read system name: %r");
	close(fd);
	host[n] = 0;
	fd = open("/sys/log/nix9", OWRITE|OCEXEC);
	if(fd < 0)
		sysfatal("cannot open /sys/log/nix9: %r");
	d = dirfstat(fd);
	if(d == nil)
		sysfatal("cannot stat /sys/log/nix9: %r");
	regular("/sys/log/nix9", d);
	if((d->mode & DMAPPEND) == 0)
		sysfatal("/sys/log/nix9 is not append-only");
	free(d);
	/* Match syslog(2)'s timestamp format, and report write failures. */
	line = smprint("%s %.15s nix9 %s %s\n", host, ctime(time(0))+4, action, system);
	length = strlen(line);
	if(write(fd, line, length) != length)
		sysfatal("cannot write /sys/log/nix9: %r");
	free(line);
	close(fd);
}

void
main(int argc, char **argv)
{
	char *path;
	Dir *d;
	int i, apply;

	if(argc == 4 && strcmp(argv[1], "event") == 0){
		event(argv[2], argv[3]);
		exits(nil);
	}
	if(argc < 4 || argc%2 != 0)
		usage();
	apply = strcmp(argv[1], "prepare") == 0;
	if(!apply && strcmp(argv[1], "check") != 0)
		usage();
	d = dirstat("/sys/log");
	if(d == nil || (d->mode & DMDIR) == 0)
		sysfatal("/sys/log is not a directory");
	free(d);
	/* Inspect every declaration before changing any file. */
	for(i = 2; i < argc; i += 2){
		path = logpath(argv[i]);
		logmode(argv[i+1]);
		d = dirstat(path);
		if(d != nil){
			regular(path, d);
			free(d);
		}
		free(path);
	}
	if(apply)
		for(i = 2; i < argc; i += 2){
			path = logpath(argv[i]);
			prepare(path, logmode(argv[i+1]));
			free(path);
		}
	exits(nil);
}
