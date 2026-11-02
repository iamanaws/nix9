/* Native /adm/users reconciliation, called only by the administrative console. */
#include "all.h"

typedef struct Entry Entry;
struct Entry {
	int id;
	char *name;
	char *leader;
	char *members;
};

typedef struct Directory Directory;
struct Directory {
	char *path;
	char *owner;
	char *group;
	ulong mode;
};

static char problem[ERRMAX];

int fs_stat(Chan*, Fcall*, Fcall*, uchar*);
int fs_wstat(Chan*, Fcall*, Fcall*, char*);

static char*
bad(char *message, char *value)
{
	snprint(problem, sizeof problem, "%s: %s", message, value);
	return problem;
}

static int
statfile(Dir *d, char *strings)
{
	Fcall in, out;
	uchar data[2048];
	int error;

	memset(&in, 0, sizeof in);
	memset(&out, 0, sizeof out);
	in.fid = FID2;
	rlock(&mainlock);
	error = fs_stat(cons.chan, &in, &out, data);
	runlock(&mainlock);
	if(error)
		return error;
	if(convM2D(out.stat, out.nstat, d, strings) == 0)
		return Econvert;
	return 0;
}

static int
wstatfile(Dir *d)
{
	Fcall in, out;
	uchar data[2048];
	char strings[2048];
	int error;

	memset(&in, 0, sizeof in);
	memset(&out, 0, sizeof out);
	in.fid = FID2;
	in.stat = data;
	in.nstat = convD2M(d, data, sizeof data);
	if(in.nstat <= BIT16SZ)
		return Econvert;
	rlock(&mainlock);
	error = fs_wstat(cons.chan, &in, &out, strings);
	runlock(&mainlock);
	return error;
}

static char*
load(char *path, int local)
{
	Dir d, *metadata;
	char strings[2048];
	char *text;
	int fd, n, used, length;

	fd = -1;
	if(local){
		fd = open(path, OREAD);
		if(fd < 0)
			return nil;
		metadata = dirfstat(fd);
		if(metadata == nil){
			close(fd);
			return nil;
		}
		d = *metadata;
		free(metadata);
	}else{
		if(walkto(path) || statfile(&d, strings) || con_open(FID2, OREAD))
			return nil;
	}
	if(d.qid.type != 0 || d.length < 0 || d.length >= 1024*1024){
		if(fd >= 0) close(fd);
		return nil;
	}
	length = d.length;
	text = malloc(1024*1024+1);
	if(text == nil){
		if(fd >= 0) close(fd);
		return nil;
	}
	used = n = 0;
	while(used < length){
		n = length-used;
		if(n > 8192) n = 8192;
		n = local ? read(fd, text+used, n) : con_read(FID2, text+used, used, n);
		if(n <= 0)
			break;
		used += n;
	}
	if(fd >= 0) close(fd);
	if(n < 0 || used != length || memchr(text, 0, used) != nil){
		free(text);
		return nil;
	}
	text[used] = 0;
	return text;
}

static int
find(Entry *entries, int count, char *name)
{
	int i;

	for(i = 0; i < count; i++)
		if(strcmp(entries[i].name, name) == 0)
			return i;
	return -1;
}

static int
validname(char *name)
{
	char *p;

	if(*name == 0 || strlen(name) >= NAMELEN)
		return 0;
	for(p = name; *p; p++)
		if((uchar)*p <= ' ' || strchr("?=+-/:,", *p) != nil)
			return 0;
	return 1;
}

static char*
table(char *text, Entry *entries, int *count, int merge)
{
	char *line, *next, *fields[5], *end;
	int i, j, id;

	for(line = text; line != nil && *line; line = next){
		next = strchr(line, '\n');
		if(next != nil) *next++ = 0;
		if(*line == 0 || *line == '#')
			continue;
		if(strlen(line) >= 4000 || getfields(line, fields, nelem(fields), 0, ":") != 4)
			return bad("invalid users entry", line);
		id = strtol(fields[0], &end, 10);
		if(*end || *fields[0] == 0 || id < -32768 || id > 32767 || !validname(fields[1]))
			return bad("invalid users identity", fields[1]);
		if(merge && (id <= 0 || strcmp(fields[1], "adm") == 0 || strcmp(fields[1], "none") == 0))
			return bad("reserved users identity", fields[1]);
		i = find(entries, *count, fields[1]);
		if(i >= 0 && (!merge || entries[i].id != id))
			return bad("existing name has another ID", fields[1]);
		for(j = 0; j < *count; j++)
			if(entries[j].id == id && i != j)
				return bad("ID belongs to another name", fields[1]);
		if(i < 0){
			if(*count >= conf.nuid)
				return bad("CWFS user table is full", fields[1]);
			i = (*count)++;
		}
		entries[i].id = id;
		entries[i].name = fields[1];
		entries[i].leader = fields[2];
		entries[i].members = fields[3];
	}
	return nil;
}

static int
pathok(char *path)
{
	char *p;

	if(path[0] != '/' || path[1] == 0 || path[strlen(path)-1] == '/')
		return 0;
	for(p = path; *p; p++)
		if((uchar)*p <= ' ' || *p == '#' || (*p == '/' &&
			(p[1] == '/' || (p[1] == '.' && (p[2] == '/' || p[2] == 0 ||
			(p[2] == '.' && (p[3] == '/' || p[3] == 0)))))))
			return 0;
	return strcmp(path, "/adm") != 0 && strncmp(path, "/adm/", 5) != 0;
}

/* Look up paths with the console's private fid, without changing permissions. */
static char*
directorycheck(char *path)
{
	Dir d;
	char strings[2048], *parent, *end, *error;

	if(walkto(path) == 0){
		if(statfile(&d, strings) || d.qid.type != QTDIR || (d.mode & ~0777) != DMDIR)
			return bad("not a regular directory", path);
		return nil;
	}
	if(strcmp(path, "/") == 0)
		return bad("cannot inspect directory", path);
	parent = strdup(path);
	end = strrchr(parent, '/');
	if(end == parent) end++;
	*end = 0;
	error = directorycheck(parent);
	free(parent);
	return error;
}

static char*
ensure(char *path, int leaf)
{
	char *parent, *end, *name, *error;

	if(walkto(path) == 0)
		return nil;
	parent = strdup(path);
	end = strrchr(parent, '/');
	name = strdup(end+1);
	if(end == parent) end++;
	*end = 0;
	error = ensure(parent, 0);
	if(error == nil && (walkto(parent) || con_create(FID2, name, -1, -1, DMDIR|(leaf ? 0700 : 0755), OREAD)))
		error = bad("cannot create directory", path);
	free(name);
	free(parent);
	return error;
}

static int
renamefile(char *path, char *name)
{
	Dir d;

	if(walkto(path))
		return -1;
	nulldir(&d);
	d.name = name;
	return wstatfile(&d);
}

static char*
save(char *text)
{
	Dir d;
	char strings[2048];
	int length;

	/* Keep the previous native table for console recovery after interruption. */
	if(walkto("/adm/users.nix9.new") == 0){
		if(statfile(&d, strings) || d.qid.type != 0 || con_remove(FID2))
			return bad("cannot remove staging file", "/adm/users.nix9.new");
	}
	if(walkto("/adm") || con_create(FID2, "users.nix9.new", -1, -1, 0664, OWRITE))
		return bad("cannot stage users table", "/adm/users.nix9.new");
	length = strlen(text);
	if(con_write(FID2, text, 0, length) != length)
		return bad("cannot write users table", "/adm/users.nix9.new");
	if(walkto("/adm/users.nix9.bak") == 0){
		if(statfile(&d, strings) || d.qid.type != 0 || con_remove(FID2))
			return bad("cannot replace backup", "/adm/users.nix9.bak");
	}
	if(renamefile("/adm/users", "users.nix9.bak"))
		return bad("cannot back up users table", "/adm/users");
	if(renamefile("/adm/users.nix9.new", "users")){
		renamefile("/adm/users.nix9.bak", "users");
		return bad("cannot select users table", "/adm/users.nix9.new");
	}
	cmd_exec("users");
	return nil;
}

char*
nix9users(char *users, char *directories, int apply)
{
	Entry *entries;
	Directory *dirs;
	Dir d;
	char strings[2048], *current, *old, *desired, *paths, *rendered, *p, *line, *next;
	char *fields[5], *end, *members, *member, *after, *error;
	int count, ndirs, i, j, groups, length;

	cmd_exec("cfs main");
	current = load("/adm/users", 0);
	old = current == nil ? nil : strdup(current);
	desired = load(users, 1);
	paths = load(directories, 1);
	entries = mallocz(conf.nuid*sizeof(Entry), 1);
	dirs = mallocz(conf.nuid*sizeof(Directory), 1);
	rendered = nil;
	count = ndirs = groups = 0;
	if(old == nil || desired == nil || paths == nil || entries == nil || dirs == nil){
		error = bad("cannot read account configuration; provision or recover /adm/users first", users);
		goto out;
	}
	error = table(old, entries, &count, 0);
	if(error == nil) error = table(desired, entries, &count, 1);
	if(error != nil) goto out;
	length = 1;
	for(i = 0; i < count; i++){
		if(*entries[i].leader && find(entries, count, entries[i].leader) < 0){
			error = bad("unknown group leader", entries[i].leader);
			goto out;
		}
		members = strdup(entries[i].members);
		for(member = members; *member; member = after){
			after = strchr(member, ',');
			if(after != nil) *after++ = 0;
			if(find(entries, count, member) < 0){
				error = bad("unknown group member", member);
				break;
			}
			groups++;
			if(after == nil) break;
		}
		free(members);
		if(error != nil) goto out;
		length += strlen(entries[i].name)+strlen(entries[i].leader)+strlen(entries[i].members)+16;
	}
	if(groups >= conf.gidspace){
		error = bad("CWFS group table is full", users);
		goto out;
	}
	for(line = paths; line != nil && *line; line = next){
		next = strchr(line, '\n');
		if(next != nil) *next++ = 0;
		if(*line == 0) continue;
		if(ndirs == conf.nuid || tokenize(line, fields, nelem(fields)) != 4 || !pathok(fields[0])){
			error = bad("invalid directory declaration", line);
			goto out;
		}
		for(j = 1; j <= 2; j++)
			if(find(entries, count, fields[j]) < 0){
				error = bad("unknown directory owner or group", fields[j]);
				goto out;
			}
		dirs[ndirs].path = fields[0];
		dirs[ndirs].owner = fields[1];
		dirs[ndirs].group = fields[2];
		dirs[ndirs].mode = strtoul(fields[3], &end, 8);
		if(*end || strlen(fields[3]) != 4 || fields[3][0] != '0' || dirs[ndirs].mode > 0777){
			error = bad("invalid directory mode", fields[3]);
			goto out;
		}
		error = directorycheck(fields[0]);
		if(error != nil) goto out;
		ndirs++;
	}
	if(!apply) goto out;
	rendered = malloc(length);
	if(rendered == nil){
		error = bad("out of memory", users);
		goto out;
	}
	p = rendered;
	for(i = 0; i < count; i++)
		p = seprint(p, rendered+length, "%d:%s:%s:%s\n", entries[i].id, entries[i].name, entries[i].leader, entries[i].members);
	if(strcmp(rendered, current) != 0)
		error = save(rendered);
	if(error != nil) goto out;
	/* Prepare paths before restrictive parent metadata, preserving file contents. */
	for(i = 0; i < ndirs; i++){
		error = ensure(dirs[i].path, 1);
		if(error != nil) goto out;
	}
	for(i = ndirs-1; i >= 0; i--){
		if(walkto(dirs[i].path) || statfile(&d, strings)){
			error = bad("cannot inspect directory", dirs[i].path);
			goto out;
		}
		if(d.mode == (DMDIR|dirs[i].mode) && strcmp(d.uid, dirs[i].owner) == 0 && strcmp(d.gid, dirs[i].group) == 0)
			continue;
		nulldir(&d);
		d.mode = DMDIR|dirs[i].mode;
		d.uid = dirs[i].owner;
		d.gid = dirs[i].group;
		if(wstatfile(&d)){
			error = bad("cannot set directory metadata", dirs[i].path);
			goto out;
		}
	}
	cmd_exec("sync");
out:
	free(current);
	free(old);
	free(desired);
	free(paths);
	free(entries);
	free(dirs);
	free(rendered);
	return error;
}

void
cmd_nix9users(int argc, char **argv)
{
	char *error;

	if(argc != 4){
		print("usage: nix9-users users-file directories-file request-id\n");
		return;
	}
	error = nix9users(argv[1], argv[2], 0);
	print("nix9-users %s %s\n", argv[3], error == nil ? "ok" : error);
}
