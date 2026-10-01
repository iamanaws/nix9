typedef struct Record Record;
struct Record {
	char tag;
	vlong count;
	double value;
	int *pointer;
};

vlong arguments(int, vlong, char*, int, int, int, int, int);
int pointers(int*, int, int (*)(int));
int callback(int);
Record record(Record, vlong);
double doubles(double, double, double, int);
float floats(float, float);
vlong conversion(double);
int variadic(char*, ...);
int recursive(int);
