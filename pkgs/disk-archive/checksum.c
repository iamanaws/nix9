#include <u.h>
#include <libc.h>
#include <libsec.h>

void
main(int argc, char **argv)
{
	DigestState *state;
	uchar buffer[IOUNIT], digest[SHA2_256dlen];
	char text[SHA2_256dlen*2+2], expected[SHA2_256dlen*2+3], *check;
	int fd, n, i;

	check = nil;
	ARGBEGIN{
	case 'c':
		check = EARGF(sysfatal("missing checksum file"));
		break;
	default:
		sysfatal("usage: disk/checksum [-c checksum-file] archive");
	}ARGEND
	if(argc != 1)
		sysfatal("usage: disk/checksum [-c checksum-file] archive");
	if((fd = open(argv[0], OREAD)) < 0)
		sysfatal("open archive: %r");
	state = sha2_256(nil, 0, nil, nil);
	if(state == nil)
		sysfatal("cannot allocate checksum state");
	while((n = read(fd, buffer, sizeof buffer)) > 0)
		sha2_256(buffer, n, nil, state);
	if(n < 0)
		sysfatal("read archive: %r");
	close(fd);
	sha2_256(nil, 0, digest, state);
	for(i = 0; i < sizeof digest; i++)
		sprint(text+2*i, "%02ux", digest[i]);
	strcat(text, "\n");
	if(check != nil){
		if((fd = open(check, OREAD)) < 0)
			sysfatal("open checksum: %r");
		n = readn(fd, expected, sizeof expected);
		if(n != sizeof text-1 || memcmp(expected, text, n) != 0)
			sysfatal("archive checksum mismatch");
		close(fd);
	}else if(write(1, text, sizeof text-1) != sizeof text-1)
		sysfatal("write checksum: %r");
	exits(nil);
}
