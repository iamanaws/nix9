{
  stdenv,
  plan9port,
  source,
}:
stdenv.mkDerivation {
  pname = "9front-mpc";
  version = "11952";
  src = source;
  nativeBuildInputs = [ plan9port ];
  postPatch = ''
    cp ${./constant.h} constant.h
    substituteInPlace sys/src/cmd/mpc.y \
      --replace-fail 'strtomp(f->s->n, nil, 0, nil)' 'constant(f->s->n)'
  '';
  buildPhase = ''
    runHook preBuild
    9 yacc sys/src/cmd/mpc.y
    9 9c -include u.h -include libc.h -include mp.h -include constant.h -o mpc.o y.tab.c
    9 9l -o mpc mpc.o
    runHook postBuild
  '';
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    echo 'bases(a,b,c,d) { a=123; b=0x7b; c=0b1111011; d=0173; }' | ./mpc > actual
    for name in a b c d; do
      grep -F "uitomp(123UL, $name);" actual
    done
    # Reference outputs from mpc in the pinned 9front image.
    mpcTool="$PWD/mpc"
    (
      cd sys/src/libsec/port
      for unit in secp256r1 secp384r1 secp256k1 jacobian; do
        printf '#include "os.h"\n#include <mp.h>\n' > "$unit.c"
        "$mpcTool" "$unit.mp" >> "$unit.c"
      done
      sha256sum -c ${./generated.sha256}
    )
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    install -Dm755 mpc "$out/bin/mpc"
    runHook postInstall
  '';
}
