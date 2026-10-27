set -euo pipefail
source=$1
output=$2
expectedHome=$3
inputsSource=$4
mkdir -p "$output"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/hello project"
cd "$work/hello project"
cp "$source/hello.c" "$source/mkfile" .
cp mkfile "$work/original.mkfile"
cp hello.c "$work/original.c"
test "$HOME" = "$expectedHome"
test "$CC" = 6c
case "$NIX9_ROOT" in "$work"/*) exit 1 ;; esac
mk
cp 6.out "$output/hello"
cmp mkfile "$work/original.mkfile"
cmp hello.c "$work/original.c"
mk clean
mkdir rules
mv mkfile rules/common.mk
printf '<rules/missing.mk\n<rules/common.mk\n' > 'build rules'
mk -f 'build rules'
cmp rules/common.mk "$work/original.mkfile"
printf '<rules/missing.mk\n<rules/common.mk\n' | cmp - 'build rules'
"$NIX9_SED" -i 's/hello from nix9/hello from cross shell/' hello.c
mk -f 'build rules'
cp 6.out "$output/edited"
6c -o direct.6 hello.c
6l -o "$output/direct" direct.6
cat > ape.c <<'C'
#include <stdio.h>
int main(void) { puts("cross shell APE PASS"); return 0; }
C
pcc -o "$output/ape" ape.c
if command -v target-only; then exit 1; fi
generate > generated.h
6c -I . -o inputs.6 "$inputsSource"
6l -o "$output/inputs" inputs.6
printf 'failure:V:\n\texit 1\n' > failure.mk
if mk -f failure.mk; then exit 1; fi
