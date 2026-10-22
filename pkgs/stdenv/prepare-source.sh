# Adapt build rules and includes on the build machine; also run after unpacking.
set -euo pipefail

sourceTree="$TMPDIR/source"
if [ ! -d "$sourceTree" ]; then sourceTree="$PWD"; fi

# Keep the source tree's layout available to upstream mkfile includes.
if [ -d "$sourceTree/sys/src" ]; then
  cp -rs --update=none "$sourceTree/sys/src/." "$NIX9_ROOT/sys/src/"
fi
for arch in 386 68000 68020 amd64 arm arm64 mips power power64 sparc sparc64; do
  if [ -d "$sourceTree/$arch/include" ]; then
    mkdir -p "$NIX9_ROOT/$arch/include"
    cp -rs --update=none "$sourceTree/$arch/include/." "$NIX9_ROOT/$arch/include/"
  fi
done

while IFS= read -r -d '' file; do
  case "$file" in
    */mkfile|*/mkfile.*|*/config|*/reduce|*/genall)
      "$NIX9_SED" -i -E \
        's@(^|[^a-zA-Z0-9_./-])/(sys|amd64|386|68000|68020|arm|arm64|mips|power|power64|sparc|sparc64|\$objtype|\$cputype)/@\1'"$NIX9_ROOT"'/\2/@g' \
        "$file"
      "$NIX9_SED" -i -E 's@(^|[^a-zA-Z0-9_./-])/bin/rc@\1'"$NIX9_SHELL"'@g' "$file"
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
  find "$sourceTree" -path "$NIX9_ROOT" -prune -o -type f -print0
  find "$NIX9_ROOT" -type f -print0
)

# mkfile.proto names /bin/mk, but Unix tools are found through PATH.
"$NIX9_SED" -i 's@MK=/bin/mk@MK=mk@' "$NIX9_ROOT/sys/src/mkfile.proto"
