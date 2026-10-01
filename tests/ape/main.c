#define _POSIX_SOURCE 1
#include <sys/types.h>
#include <sys/wait.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void
check(int condition, const char *name)
{
	if(!condition){
		fprintf(stderr, "FAIL: %s (errno=%d)\n", name, errno);
		exit(1);
	}
}

static void
memory(void)
{
	unsigned char *p, *grown, *zero;
	int i;

	p = malloc(257);
	check(p != NULL, "malloc");
	for(i = 0; i < 257; i++)
		p[i] = i % 251;
	grown = realloc(p, 8192);
	check(grown != NULL, "realloc");
	for(i = 0; i < 257; i++)
		check(grown[i] == i % 251, "realloc preserves bytes");
	memset(grown + 257, 0xa5, 8192 - 257);
	check(grown[8191] == 0xa5, "expanded allocation");
	free(grown);
	zero = calloc(37, 13);
	check(zero != NULL, "calloc");
	for(i = 0; i < 37 * 13; i++)
		check(zero[i] == 0, "calloc clears bytes");
	free(zero);
	puts("PASS: memory allocation");
}

static void
stdio_test(void)
{
	FILE *f;
	unsigned char input[8193], output[8193];
	int i;

	for(i = 0; i < sizeof input; i++)
		input[i] = i % 256;
	f = fopen("stdio.dat", "w+b");
	check(f != NULL, "fopen");
	check(fwrite(input, 1, sizeof input, f) == sizeof input, "fwrite");
	check(fflush(f) == 0, "fflush");
	check(ftell(f) == sizeof input, "ftell");
	check(fseek(f, 0, SEEK_SET) == 0, "fseek");
	check(fread(output, 1, sizeof output, f) == sizeof output, "fread");
	check(memcmp(input, output, sizeof input) == 0, "stdio bytes");
	check(fgetc(f) == EOF && feof(f) && !ferror(f), "stdio EOF");
	check(fclose(f) == 0, "fclose");
	check(remove("stdio.dat") == 0, "remove");
	puts("PASS: buffered file IO");
}

static void
files(void)
{
	int fd;
	char data[4];

	fd = open("fd.dat", O_CREAT | O_EXCL | O_RDWR, 0600);
	check(fd >= 0, "open");
	check(write(fd, "A\0Z", 3) == 3, "write");
	check(lseek(fd, 0, SEEK_SET) == 0, "lseek");
	check(read(fd, data, sizeof data) == 3, "read");
	check(memcmp(data, "A\0Z", 3) == 0, "descriptor bytes");
	check(read(fd, data, 1) == 0, "descriptor EOF");
	check(close(fd) == 0, "close");
	check(unlink("fd.dat") == 0, "unlink");
	errno = 0;
	check(open("fd.dat", O_RDONLY) == -1 && errno == ENOENT, "missing file errno");
	puts("PASS: file descriptors and errno");
}

static void
processes(const char *self)
{
	int fds[2], status;
	pid_t pid;
	char output[32];
	ssize_t count;
	size_t used;

	check(fflush(NULL) == 0, "flush before fork");
	check(pipe(fds) == 0, "pipe");
	pid = fork();
	check(pid >= 0, "fork");
	if(pid == 0){
		close(fds[0]);
		if(dup2(fds[1], STDOUT_FILENO) == -1)
			_exit(120);
		close(fds[1]);
		execl(self, self, "--child", (char *)NULL);
		_exit(121);
	}
	check(close(fds[1]) == 0, "close pipe writer");
	used = 0;
	while((count = read(fds[0], output + used, sizeof output - used)) > 0){
		used += count;
		check(used < sizeof output, "child output length");
	}
	check(count == 0, "pipe EOF");
	check(close(fds[0]) == 0, "close pipe reader");
	check(waitpid(pid, &status, 0) == pid, "waitpid");
	check(WIFEXITED(status) && WEXITSTATUS(status) == 23, "child exit status");
	check(used == 10 && memcmp(output, "ape-child\n", 10) == 0, "exec output");
	puts("PASS: pipe fork exec and wait");
}

int
main(int argc, char **argv)
{
	if(argc == 2 && strcmp(argv[1], "--child") == 0){
		if(write(STDOUT_FILENO, "ape-child\n", 10) != 10)
			return 122;
		return 23;
	}
	check(argc == 1, "arguments");
	memory();
	stdio_test();
	files();
	processes(argv[0]);
	return 0;
}
