#include <u.h>
#include <libc.h>
#include <answer.h>
#include "generated.h"

void
main(void)
{
	if(answer() != GENERATED_ANSWER)
		sysfatal("wrong library or generator");
	print("cross stdenv PASS\n");
	exits(nil);
}
