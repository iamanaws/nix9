#include <u.h>
#include <libc.h>
#include "git.h"

static void
exporttree(Hash hash, char *path, int depth)
{
	Object *tree, *blob;
	Dirent *entry;
	char *child;
	vlong offset;
	int i, fd, n;

	if(depth > 128)
		sysfatal("tree too deep");
	if((tree = readobject(hash)) == nil || tree->type != GTree)
		sysfatal("expected tree %H", hash);
	if((fd = create(path, OREAD, DMDIR|0755)) < 0)
		sysfatal("create %s: %r", path);
	close(fd);
	for(i = 0; i < tree->tree->nent; i++){
		entry = &tree->tree->ent[i];
		if(entry->islink || entry->ismod)
			sysfatal("unsupported symlink or submodule: %s/%s", path, entry->name);
		if(entry->name[0] == 0 || strchr(entry->name, '/') != nil
		|| strcmp(entry->name, ".") == 0 || strcmp(entry->name, "..") == 0
		|| strcmp(entry->name, ".git") == 0)
			sysfatal("invalid tree entry: %s", entry->name);
		child = smprint("%s/%s", path, entry->name);
		if(child == nil)
			sysfatal("out of memory");
		if(access(child, AEXIST) == 0)
			sysfatal("duplicate tree entry: %s", child);
		if(entry->mode & DMDIR)
			exporttree(entry->h, child, depth+1);
		else{
			if((blob = readobject(entry->h)) == nil || blob->type != GBlob)
				sysfatal("expected blob %H", entry->h);
			if((fd = create(child, OWRITE, entry->mode & 0111 ? 0755 : 0644)) < 0)
				sysfatal("create %s: %r", child);
			for(offset = 0; offset < blob->size; offset += n){
				n = blob->size - offset > 65536 ? 65536 : blob->size - offset;
				if(write(fd, blob->data + offset, n) != n)
					sysfatal("write %s: %r", child);
			}
			close(fd);
			unref(blob);
		}
		free(child);
	}
	unref(tree);
}

void
main(int argc, char **argv)
{
	Hash hash;
	Object *commit;

	if(argc != 3 || strlen(argv[1]) != 40)
		sysfatal("usage: %s COMMIT OUTPUT", argv[0]);
	gitinit(nil, 0, nil);
	gitdirmode = 0755;
	if(hparse(&hash, argv[1]) < 0)
		sysfatal("invalid commit hash");
	if((commit = readobject(hash)) == nil || commit->type != GCommit)
		sysfatal("expected commit %H", hash);
	exporttree(commit->commit->tree, argv[2], 0);
	unref(commit);
	exits(nil);
}
