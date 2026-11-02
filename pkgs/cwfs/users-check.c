/* Ask the private CWFS console to validate a proposed table without applying it. */
#include <u.h>
#include <libc.h>
#include <bio.h>

void
main(int argc, char **argv)
{
	Biobuf input;
	char request[64], marker[96], *line;
	int fd, lockfd;

	if(argc != 4)
		sysfatal("usage: cwfs-users command-service users-file directories-file");
	/* ORCLOSE releases this administrative check lock even on interruption. */
	lockfd = create("/srv/nix9-cwfs-users-lock", OWRITE|OEXCL|ORCLOSE, 0600);
	if(lockfd < 0)
		sysfatal("another CWFS account check is running: %r");
	fd = open(argv[1], ORDWR);
	if(fd < 0)
		sysfatal("open CWFS administrative console: %r");
	snprint(request, sizeof request, "%d-%llud", getpid(), nsec());
	snprint(marker, sizeof marker, "nix9-users %s ", request);
	alarm(10000);
	if(fprint(fd, "nix9-users %s %s %s\n", argv[2], argv[3], request) < 0)
		sysfatal("request CWFS account check: %r");
	Binit(&input, fd, OREAD);
	while((line = Brdstr(&input, '\n', 1)) != nil){
		if(strncmp(line, marker, strlen(marker)) == 0){
			line += strlen(marker);
			if(strcmp(line, "ok") != 0)
				sysfatal("CWFS accounts: %s", line);
			alarm(0);
			exits(nil);
		}
		free(line);
	}
	sysfatal("CWFS account check did not reply; boot a CWFS version with account support");
}
