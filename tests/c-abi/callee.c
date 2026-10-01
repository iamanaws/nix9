#include <u.h>
#include <libc.h>
#include "abi.h"

vlong
arguments(int a, vlong b, char *c, int d, int e, int f, int g, int h)
{
	return a + b + c[1] + d*2 + e*3 + f*4 + g*5 + h*6;
}

int
pointers(int *values, int n, int (*fn)(int))
{
	int i, total;
	total = 0;
	for(i = 0; i < n; i++){
		values[i] = fn(values[i]);
		total += values[i];
	}
	return total;
}

Record
record(Record r, vlong increment)
{
	r.tag++;
	r.count += increment;
	r.value *= 2;
	*r.pointer += 7;
	return r;
}

double
doubles(double a, double b, double c, int n)
{
	return (a + b) * c + n;
}

float
floats(float a, float b)
{
	return a + b;
}

vlong
conversion(double a)
{
	return (vlong)a;
}

int
variadic(char *label, ...)
{
	va_list args;
	int a;
	double b;
	vlong c;
	char *d;
	Record *e;

	va_start(args, label);
	a = va_arg(args, int);
	b = va_arg(args, double);
	c = va_arg(args, vlong);
	d = va_arg(args, char*);
	e = va_arg(args, Record*);
	va_end(args);
	return strcmp(label, "values") == 0 && a == -17 && b == 2.5
		&& c == 0x100000003LL && strcmp(d, "tail") == 0 && e->count == 41;
}

int
recursive(int n)
{
	if(n < 2)
		return 1;
	return n * recursive(n-1);
}
