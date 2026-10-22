{
  pkgs,
  python,
  testSupport,
  vm,
  ar,
  cc,
  mk,
  rc,
  sysroot,
  libc,
  libbio,
  libmach,
  libap,
  libbsd,
}:
pkgs.runCommand "9front-native-tools" { requiredSystemFeatures = [ "kvm" ]; } ''
  ${python}/bin/python ${
    testSupport [
      ../../tests/export_tree.py
      ../../tests/artifacts.py
    ]
  }/export_tree.py \
    ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
    "$TMPDIR/tools.tar" amd64/bin/awk \
    amd64/bin/bind amd64/bin/cpp amd64/bin/pcc amd64/bin/tar amd64/bin/gunzip \
    amd64/bin/cat amd64/bin/chmod amd64/bin/sed amd64/bin/webfs amd64/bin/cp amd64/bin/echo amd64/bin/mpc amd64/bin/mkdir amd64/bin/test \
    amd64/bin/rm amd64/bin/mv amd64/bin/pwd amd64/bin/ls amd64/bin/grep amd64/bin/tr amd64/bin/ed amd64/bin/date \
    amd64/mkfile sys/src/mkfile.proto sys/src/cmd/mkone sys/src/cmd/mklib sys/src/cmd/mkmany sys/src/cmd/mksyslib rc/lib/rcmain
  tar -xf "$TMPDIR/tools.tar"
  mkdir -p "$out/bin" "$out/sys" "$out/amd64/lib"
  cp amd64/bin/* "$out/bin/"
  mkdir -p "$out/bootstrap/bin" "$out/bootstrap/rc/bin" "$out/bootstrap/lib"
  cp ${ar}/bin/ar "$out/bootstrap/bin/ar"
  cp ${cc}/bin/* "$out/bootstrap/bin/"
  cp ${mk}/bin/mk "$out/bootstrap/bin/mk"
  cp ${rc}/bin/rc "$out/bootstrap/rc/bin/rc"
  cp rc/lib/rcmain "$out/rcmain"
  cp -r ${sysroot}/sys/include "$out/sys/"
  cp -r ${sysroot}/amd64/include "$out/amd64/"
  cp amd64/mkfile "$out/amd64/"
  cp -r sys/src "$out/sys/"
  cp ${libc}/lib/libc.a ${libbio}/lib/libbio.a ${libmach}/lib/libmach.a "$out/bootstrap/lib/"
  mkdir -p "$out/amd64/lib/ape"
  cp ${libap}/lib/libap.a ${libbsd}/lib/libbsd.a "$out/amd64/lib/ape/"
''
