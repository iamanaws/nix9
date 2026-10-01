#include <u.h>
#include <libc.h>
#include "abi.h"

void
check(int condition, char *name)
{
	if(!condition)
		sysfatal("FAIL: %s", name);
}

int
callback(int value)
{
	return value * 3 - 1;
}

void
main(int argc, char **argv)
{
	int values[3], cell;
	Record input, output;
	char buf[64];
	float promoted;

	check(argc == 3 && strcmp(argv[1], "alpha") == 0 && strcmp(argv[2], "23") == 0, "argv");
	check(sizeof(int) == 4 && sizeof(long) == 4 && sizeof(vlong) == 8
		&& sizeof(void*) == 8, "data model");
	print("PASS: arguments and data model\n");

	check(arguments(-7, 0x100000003LL, "AZ", 2, -3, 4, -5, 6)
		== 0x10000006cLL, "mixed integer arguments");
	check(recursive(7) == 5040, "recursion");
	print("PASS: integer calls and recursion\n");

	values[0] = 2;
	values[1] = -3;
	values[2] = 7;
	check(pointers(values, 3, callback) == 15, "callback result");
	check(values[0] == 5 && values[1] == -10 && values[2] == 20, "pointer writes");
	print("PASS: pointers and callbacks\n");

	cell = 10;
	input.tag = 'A';
	input.count = 41;
	input.value = 1.25;
	input.pointer = &cell;
	output = record(input, 0x100000000LL);
	check(input.tag == 'A' && input.count == 41 && input.value == 1.25, "struct copy");
	check(output.tag == 'B' && output.count == 0x100000029LL
		&& output.value == 2.5 && output.pointer == &cell && cell == 17, "struct return");
	print("PASS: structures by value and return\n");

	check(doubles(1.25, 2.5, 3.0, 3) == 14.25, "double arguments and return");
	check(floats(2.5, 3.25) == 5.75, "float arguments and return");
	check(conversion(-4294967299.0) == -4294967299LL, "double to vlong");
	print("PASS: floating point\n");

	promoted = 2.5;
	check(variadic("values", (short)-17, promoted, 0x100000003LL, "tail", &input), "varargs");
	snprint(buf, sizeof(buf), "%d %lld %s", -17, 0x100000003LL, "tail");
	check(strcmp(buf, "-17 4294967299 tail") == 0, "libc varargs");
	print("PASS: varargs and libc calls\n");
	exits(nil);
}
