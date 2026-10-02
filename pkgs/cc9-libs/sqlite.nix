{
  runCommand,
  fetchurl,
  llvmPackages,
  unzip,
  cc9,
}:
let
  source = fetchurl {
    url = "https://www.sqlite.org/2026/sqlite-amalgamation-3510200.zip";
    hash = "sha256:6e2a845a493026bdbad0618b2b5a0cf48584faab47384480ed9f592d912f23ec";
  };
in
runCommand "cc9-sqlite-3.51.2" { nativeBuildInputs = [ unzip ]; } ''
  runtime=${cc9}
  source ${cc9.setup}
  unzip -q ${source}
  cd sqlite-amalgamation-3510200
  patch -p1 < ${./sqlite.patch}
  cp ${./plan9-lock.c} plan9-lock.c
  ${llvmPackages.clang-unwrapped}/bin/clang \
    "''${cc9Flags[@]}" -std=c11 -O2 -femulated-tls \
    -DSQLITE_OS_UNIX=1 -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION=1 \
    -DSQLITE_MAX_MMAP_SIZE=0 -DSQLITE_OMIT_WAL=1 \
    '-DSQLITE_DEFAULT_UNIX_VFS="unix-plan9"' \
    -c sqlite3.c -o sqlite3.o
  mkdir -p "$out/lib" "$out/include"
  ${llvmPackages.llvm}/bin/llvm-ar rcs "$out/lib/libsqlite3.a" sqlite3.o
  cp sqlite3.h "$out/include/"
''
