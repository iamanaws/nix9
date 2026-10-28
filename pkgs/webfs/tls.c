#include <u.h>
#include <libc.h>
#include <ctype.h>
#include <thread.h>
#include <mp.h>
#include <libsec.h>

#include "dat.h"
#include "fns.h"

/* Host files bind an exact certificate to a host, rather than trusting a CA.
 * Use the native thumbprint record format, restricted to SHA-256 certificates.
 * Both files must be readable; includes and malformed records fail closed. */
static int
pinfile(char *path, uchar *hash)
{
	char *data, *line, *next, *field[3], error[ERRMAX];
	uchar pin[SHA2_256dlen];
	int fd, n, m, i, found;

	if((fd = open(path, OREAD|OCEXEC)) < 0){
		rerrstr(error, sizeof(error));
		werrstr("TLS policy %s: %s", path, error);
		return -1;
	}
	data = emalloc(65537);
	n = 0;
	found = -1;
	while(n < 65537){
		m = read(fd, data+n, 65537-n);
		if(m < 0)
			goto Out;
		if(m == 0)
			break;
		n += m;
	}
	if(n > 65536){
		werrstr("file exceeds 64 KiB");
		goto Out;
	}
	if(memchr(data, 0, n) != nil){
		werrstr("NUL in thumbprint file");
		goto Out;
	}
	data[n] = 0;
	found = 0;
	for(line = data; line; line = next){
		if(next = strchr(line, '\n'))
			*next++ = 0;
		m = getfields(line, field, nelem(field), 1, " \t\r");
		if(m == 0)
			continue;
		if(field[0][0] == '#' && strcmp(field[0], "#include") != 0)
			continue;
		if(m < 2 || strcmp(field[0], "x509") != 0
		|| strncmp(field[1], "sha256=", 7) != 0 || strlen(field[1]+7) != 64)
			goto Malformed;
		for(i = 0; i < 64; i++)
			if(!isxdigit((uchar)field[1][7+i]))
				goto Malformed;
		if(dec16(pin, sizeof(pin), field[1]+7, 64) != sizeof(pin))
			goto Malformed;
		if(memcmp(pin, hash, sizeof(pin)) == 0)
			found = 1;
	}
	goto Out;
Malformed:
	found = -1;
	werrstr("expected x509 sha256=<64 hex digits>");
Out:
	rerrstr(error, sizeof(error));
	close(fd);
	free(data);
	if(found < 0)
		werrstr("TLS policy %s: %s", path, error);
	return found;
}

char*
tlshostname(char *name)
{
	char *host, *p;
	int n;

	if(name == nil)
		goto Bad;
	host = smprint("%N", name);
	if(host == nil)
		return nil;
	n = strlen(host);
	if(n > 0 && host[n-1] == '.')
		host[--n] = 0;
	if(n == 0 || n >= Domlen || host[0] == '.' || strstr(host, "..") != nil)
		goto Free;
	for(p = host; *p; p++){
		if(!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z')
		|| (*p >= '0' && *p <= '9') || strchr(".-_:", *p)))
			goto Free;
		*p = tolower(*p);
	}
	return host;
Free:
	free(host);
Bad:
	werrstr("invalid TLS host name");
	return nil;
}

int
tlstrust(char *host, uchar *hash)
{
	char *path;
	int n;

	path = smprint("%s/revoked", tlstrustdir);
	if(path == nil)
		return -1;
	n = pinfile(path, hash);
	free(path);
	if(n < 0)
		return -1;
	if(n){
		werrstr("TLS certificate for %s is revoked", host);
		return -1;
	}
	path = smprint("%s/hosts/%s", tlstrustdir, host);
	if(path == nil)
		return -1;
	n = pinfile(path, hash);
	free(path);
	if(n < 0)
		return -1;
	if(!n){
		werrstr("TLS certificate for %s is not trusted", host);
		return -1;
	}
	return 0;
}
