#include <u.h>
#include <libc.h>
#include <mp.h>

static void
check(char *name, mpint *n, char *expected)
{
	char buf[256];

	snprint(buf, sizeof buf, "%.16B", n);
	if(strcmp(buf, expected) != 0)
		sysfatal("%s: got %s, expected %s", name, buf, expected);
}

void
main(void)
{
	mpint *a, *b, *p, *n, *r, *e;
	uchar bytes[16];

	fmtinstall('B', mpfmt);
	a = strtomp("123456789ABCDEF0FEDCBA9876543210", nil, 16, nil);
	b = strtomp("FEDCBA98765432100123456789ABCDEF", nil, 16, nil);
	p = strtomp("7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", nil, 16, nil);
	n = mpnew(0);
	r = mpnew(0);
	e = uitomp(65537, nil);

	/* Expected values calculated independently with Python integers. */
	mpadd(a, b, n);
	check("add", n, "11111111111111100FFFFFFFFFFFFFFFF");
	mpsub(a, b, n);
	check("subtract", n, "-ECA8641FDB97531F02468ACF13579BDF");
	mpmul(a, b, n);
	check("multiply", n, "121FA00AD77D7423213D0003E234949AAA6C876160EC6A522236D88FE5618CF0");
	mpdiv(b, a, n, r);
	check("quotient", n, "E");
	check("remainder", r, "E2111111111111110F");
	mpinvert(a, p, n);
	check("inverse", n, "62CFEFE6EB41053969967BD711C5169F");
	mpexp(a, e, p, n);
	check("power", n, "79CEE16D903910E02388A333B3C87C22");

	strtomp("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", nil, 16, n);
	mpadd(n, mpone, n);
	check("carry and aliasing", n, "100000000000000000000000000000000");
	mpsub(n, mpone, n);
	check("borrow and aliasing", n, "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF");
	mptober(a, bytes, sizeof bytes);
	betomp(bytes, sizeof bytes, n);
	check("byte conversion", n, "123456789ABCDEF0FEDCBA9876543210");

	mpfree(a);
	mpfree(b);
	mpfree(p);
	mpfree(n);
	mpfree(r);
	mpfree(e);
	exits(nil);
}
