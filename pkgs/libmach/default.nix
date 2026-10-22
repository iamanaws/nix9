{
  mkPlan9Library,
  source,
  python3,
}:
mkPlan9Library {
  name = "libmach";
  src = "${source}/sys/src/libmach";
  includeDirs = [
    source
    "${source}/sys/src/cmd"
  ];
  postPatch = ''
    sed -i 's|"/\([^"]*/include/ureg.h\)"|"\1"|' *.c
    # The cross-compiler predates binary integer literals.
    ${python3}/bin/python - <<'PY'
    from pathlib import Path
    import re
    path = Path("qdb.c")
    path.write_text(re.sub(r"\b0b[01]+\b", lambda m: hex(int(m[0], 2)), path.read_text()))
    PY
  '';
}
