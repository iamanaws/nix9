{
  stdenv,
  plan9port,
  source,
}:
stdenv.mkDerivation {
  name = "build-pcc";
  dontUnpack = true;
  nativeBuildInputs = [ plan9port ];
  buildPhase = ''
    cp ${source}/sys/src/cmd/pcc.c pcc.c
    substituteInPlace pcc.c \
      --replace-fail '"/bin/%s"' '"%s"' \
      --replace-fail '"/bin/cpp"' '"cpp"' \
      --replace-fail 'exec(c, a->strings)' 'execvp(c, a->strings)' \
      --replace-fail 'exec(c1, a1->strings)' 'execvp(c1, a1->strings)' \
      --replace-fail 'exec(c2, a2->strings)' 'execvp(c2, a2->strings)' \
      --replace-fail 'smprint("/%s/lib/ape/lib%s.a", ot->name, ARGF())' \
        'smprint("%s/%s/lib/ape/lib%s.a", getenv("NIX9_ROOT"), ot->name, ARGF())' \
      --replace-fail 'smprint("/%s/lib/ape/libap.a", ot->name)' \
        'smprint("%s/%s/lib/ape/libap.a", getenv("NIX9_ROOT"), ot->name)' \
      --replace-fail 'smprint("-I/%s/include/ape", ot->name)' \
        'smprint("-I%s/%s/include/ape", getenv("NIX9_ROOT"), ot->name)' \
      --replace-fail 'append(&cpp, "-I/sys/include/ape")' \
        'append(&cpp, smprint("-I%s/sys/include/ape", getenv("NIX9_ROOT")))' \
      --replace-fail 'append(&ld, ot->ld);' \
        'append(&ld, ot->ld); append(&ld, "-l"); append(&ld, "-E"); append(&ld, "_main");' \
      --replace-fail 'doexec(smprint("%s", ot->ld), &ld);' \
        'append(&ld, smprint("%s/%s/lib/ape/libbsd.a", getenv("NIX9_ROOT"), ot->name));
         append(&ld, smprint("%s/%s/lib/ape/libap.a", getenv("NIX9_ROOT"), ot->name));
         doexec(smprint("%s", ot->ld), &ld);'
    9 9c pcc.c
    9 9l -o pcc pcc.o
  '';
  installPhase = ''
    install -Dm755 pcc "$out/bin/pcc"
  '';
}
