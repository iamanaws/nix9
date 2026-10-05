#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 3 ]]; then
  echo "usage: $0 RUNTIME ELF2AOUT OUTPUT" >&2
  exit 2
fi
runtime=$(realpath "$1")
converter=$(realpath "$2")
output=$3
sources=$(cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$output"
flags=(
  --target=x86_64-unknown-none -D__plan9__ -fno-pic
  -ffunction-sections -fdata-sections -femulated-tls
  -isystem "$runtime/sysinc/cxxv1" -isystem "$runtime/sysinc/cc9"
  -std=c++23 -nostdinc++ -nostdlib
  -D_LIBCPP_PROVIDES_DEFAULT_RUNE_TABLE -D_LIBCPP_HAS_CLOCK_GETTIME
)
"${CXX:-clang++}" "${flags[@]}" -c "$sources/runtime.cpp" -o "$output/runtime.o"
startup=()
# Releases keep crt0 in the archive; a locally rebuilt object takes precedence.
if [[ -f "$runtime/crt0.o" ]]; then startup=("$runtime/crt0.o"); fi
"${LD:-ld.lld}" --gc-sections -static -nostdlib -T "$runtime/plan9.ld" \
  -o "$output/runtime.elf" --start-group "${startup[@]}" "$output/runtime.o" \
  "$runtime/libcc9cxx.a" "$runtime/libcc9m.a" --end-group
"${PYTHON:-python3}" "$converter" "$output/runtime.elf" "$output/runtime-tests"
