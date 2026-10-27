# Adapt build rules and includes on the build machine; also run after unpacking.
set -euo pipefail

mkPaths='s@(^|[^a-zA-Z0-9_./-])/(sys|amd64|386|68000|68020|arm|arm64|mips|power|power64|sparc|sparc64|\$objtype|\$cputype)/@\1'"$NIX9_ROOT"'/\2/@g'
mkShell='s@(^|[^a-zA-Z0-9_./-])/bin/rc@\1'"$NIX9_SHELL"'@g'

if [ "${1:-}" = --mkfile ]; then
  if [ ! -r "${2:?missing mkfile}" ]; then
    printf 'warning: skipping missing include file %s\n' "$2" >&2
    exit
  fi
  "$NIX9_SED" -E -e "$mkPaths" -e "$mkShell" \
    -e "s@^<([^|])@<|$BASH $0 --mkfile \1@" "${2:?missing mkfile}"
  exit
fi

sourceTree="$TMPDIR/source"
if [ ! -d "$sourceTree" ]; then sourceTree="$PWD"; fi
if [ "${1:-}" = --root ]; then sourceTree=; fi

# Keep the source tree's layout available to upstream mkfile includes.
if [ -n "$sourceTree" ] && [ -d "$sourceTree/sys/src" ]; then
  cp -rs --update=none "$sourceTree/sys/src/." "$NIX9_ROOT/sys/src/"
fi
for arch in 386 68000 68020 amd64 arm arm64 mips power power64 sparc sparc64; do
  if [ -n "$sourceTree" ] && [ -d "$sourceTree/$arch/include" ]; then
    mkdir -p "$NIX9_ROOT/$arch/include"
    cp -rs --update=none "$sourceTree/$arch/include/." "$NIX9_ROOT/$arch/include/"
  fi
done

while IFS= read -r -d '' file; do
  case "$file" in
    */mkfile|*/mkfile.*|*/config|*/reduce|*/genall)
      "$NIX9_SED" -i -E -e "$mkPaths" -e "$mkShell" "$file"
      ;;
    *.c|*.h|*.s)
      "$NIX9_SED" -i -E '/^[[:space:]]*#[[:space:]]*include/s@(["<])/(sys|amd64|386|68000|68020|arm|arm64|mips|power|power64|sparc|sparc64)/@\1'"$NIX9_ROOT"'/\2/@' "$file"
      ;;
  esac
  # Source generators must execute the build machine's rc.
  prefix=
  IFS= read -r -n 9 prefix < "$file" || :
  if [ "$prefix" = '#!/bin/rc' ]; then
    "$NIX9_SED" -i "1s@/bin/rc@$NIX9_SHELL@" "$file"
  fi
done < <(
  if [ -n "$sourceTree" ]; then
    find "$sourceTree" -path "$NIX9_ROOT" -prune -o -type f -print0
  fi
  find "$NIX9_ROOT" -type f -print0
)

# mkfile.proto names /bin/mk, but Unix tools are found through PATH.
"$NIX9_SED" -i 's@MK=/bin/mk@MK=mk@' "$NIX9_ROOT/sys/src/mkfile.proto"
