# Sourced by APE builds with gcc, 6c, 6l, and ccroot in the environment.
apeIncludeDir="$TMPDIR/ape-include"
cp -r "$ccroot/amd64/include/ape" "$apeIncludeDir"
chmod -R u+w "$apeIncludeDir"
substituteInPlace "$apeIncludeDir"/{stddef,stdint}.h \
  --replace-fail '"/sys/include/ape/' '"'"$ccroot"'/sys/include/ape/'

apeCompile() {
  local source="$1" object="$2" standard="${3:-c99}"
  gcc -E -P -undef -nostdinc -D_Noreturn= \
    -std="$standard" "${@:4}" \
    -I "$apeIncludeDir" -I "$ccroot/sys/include/ape" "$source" -o "$object.i"
  6c -o "$object" "$object.i"
}

apeLink() {
  # Ignore absolute guest library pragmas. The two APE libraries refer to
  # one another, so resolve libap again after libbsd.
  6l -H2 -l -E _main -o "$@" \
    "$ccroot/amd64/lib/ape/libap.a" \
    "$ccroot/amd64/lib/ape/libbsd.a" \
    "$ccroot/amd64/lib/ape/libap.a"
}
