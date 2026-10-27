{
  pkgs,
  imageTools,
  buildTools,
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
pkgs.runCommand "9front-native-tools" { } ''
  mkdir -p "$out/bin" "$out/sys" "$out/amd64/lib"
  cp ${imageTools}/amd64/bin/* "$out/bin/"
  cp ${buildTools}/bin/* "$out/bin/"
  mkdir -p "$out/bootstrap/bin" "$out/bootstrap/rc/bin" "$out/bootstrap/lib"
  cp ${ar}/bin/ar "$out/bootstrap/bin/ar"
  cp ${cc}/bin/* "$out/bootstrap/bin/"
  cp ${mk}/bin/mk "$out/bootstrap/bin/mk"
  cp ${rc}/bin/rc "$out/bootstrap/rc/bin/rc"
  cp ${sysroot}/rc/lib/rcmain "$out/rcmain"
  cp -r ${sysroot}/sys/include "$out/sys/"
  cp -r ${sysroot}/amd64/include "$out/amd64/"
  cp ${sysroot}/amd64/mkfile "$out/amd64/"
  cp -r ${sysroot}/sys/src "$out/sys/"
  cp ${libc}/lib/libc.a ${libbio}/lib/libbio.a ${libmach}/lib/libmach.a "$out/bootstrap/lib/"
  mkdir -p "$out/amd64/lib/ape"
  cp ${libap}/lib/ape/libap.a ${libbsd}/lib/ape/libbsd.a "$out/amd64/lib/ape/"
''
