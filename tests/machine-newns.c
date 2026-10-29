#include <u.h>
#include <libc.h>
#include <auth.h>

void
main(int argc, char **argv)
{
  if(argc != 2)
    sysfatal("expected an rc command");
  if(newns(getuser(), nil) < 0)
    sysfatal("newns: %r");
  execl("/bin/rc", "rc", "-e", "-c", argv[1], nil);
  sysfatal("exec rc: %r");
}
