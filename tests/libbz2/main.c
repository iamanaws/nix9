#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bzlib.h"

#define CAPACITY (4 * 1024 * 1024)

static void
check(int condition, const char *message)
{
	if(!condition){
		fprintf(stderr, "FAIL: %s\n", message);
		exit(1);
	}
}

static void
errors(void)
{
	char compressed[256], output[256];
	unsigned int size, outsize;

	size = sizeof compressed;
	check(BZ2_bzBuffToBuffCompress(compressed, &size, "sample", 6, 1, 0, 30) == BZ_OK,
		"prepare compressed data");
	outsize = 1;
	check(BZ2_bzBuffToBuffDecompress(output, &outsize, compressed, size, 0, 0) == BZ_OUTBUFF_FULL,
		"short output buffer");
	outsize = sizeof output;
	check(BZ2_bzBuffToBuffDecompress(output, &outsize, compressed, size - 1, 0, 0) == BZ_UNEXPECTED_EOF,
		"truncated input");
	compressed[0] = '!';
	outsize = sizeof output;
	check(BZ2_bzBuffToBuffDecompress(output, &outsize, compressed, size, 0, 0) == BZ_DATA_ERROR_MAGIC,
		"invalid header");
	size = sizeof compressed;
	check(BZ2_bzBuffToBuffCompress(compressed, &size, "sample", 6, 0, 0, 30) == BZ_PARAM_ERROR,
		"invalid compression level");
	puts("PASS: libbz2 error handling");
}

int
main(int argc, char **argv)
{
	FILE *file;
	char *input, *output;
	unsigned int size, outsize;
	int result;

	if(argc == 2 && strcmp(argv[1], "--errors") == 0){
		errors();
		return 0;
	}
	check(argc == 4, "expected compress/decompress input output");
	input = malloc(CAPACITY);
	output = malloc(CAPACITY);
	check(input != NULL && output != NULL, "allocation");
	file = fopen(argv[2], "rb");
	check(file != NULL, "open input");
	size = fread(input, 1, CAPACITY, file);
	check(!ferror(file) && fgetc(file) == EOF, "read input within limit");
	check(fclose(file) == 0, "close input");
	outsize = CAPACITY;
	if(strcmp(argv[1], "compress") == 0)
		result = BZ2_bzBuffToBuffCompress(output, &outsize, input, size, 1, 0, 30);
	else {
		check(strcmp(argv[1], "decompress") == 0, "unknown mode");
		result = BZ2_bzBuffToBuffDecompress(output, &outsize, input, size, 0, 0);
	}
	check(result == BZ_OK, "compression/decompression");
	file = fopen(argv[3], "wb");
	check(file != NULL, "open output");
	check(fwrite(output, 1, outsize, file) == outsize, "write output");
	check(fclose(file) == 0, "close output");
	free(input);
	free(output);
	return 0;
}
