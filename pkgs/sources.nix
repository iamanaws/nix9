{
  pkgs,
  python,
  testSupport,
  vm,
}:
let
  exportSource =
    name:
    {
      paths,
      check ? "",
    }:
    pkgs.runCommand name { requiredSystemFeatures = [ "kvm" ]; } (
      ''
        ${python}/bin/python ${
          testSupport [
            ../tests/export_tree.py
            ../tests/artifacts.py
          ]
        }/export_tree.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 "$TMPDIR/source.tar" \
          ${pkgs.lib.replaceStrings [ "\n" ] [ "\n  " ] paths}
        mkdir -p "$out"
        tar -xf "$TMPDIR/source.tar" -C "$out"
      ''
      + check
    );
in
{
  sysroot =
    pkgs.runCommand "9front-11952-amd64-sysroot"
      {
        requiredSystemFeatures = [ "kvm" ];
      }
      ''
        ${python}/bin/python ${
          testSupport [
            ../tests/export_tree.py
            ../tests/artifacts.py
          ]
        }/export_tree.py \
          ${pkgs.qemu}/bin/qemu-system-x86_64 \
          ${vm}/9front.qcow2 "$TMPDIR/sysroot.tar" sys/include amd64/include amd64/lib
        mkdir -p "$out"
        tar -xf "$TMPDIR/sysroot.tar" -C "$out"
        test -s "$out/amd64/lib/libc.a"
        test -s "$out/sys/include/libc.h"
      '';
  apeSource = exportSource "9front-ape-source" {
    paths = "sys/src/ape sys/src/libc";
  };
  secSource = exportSource "9front-libsec-source" {
    paths = "sys/src/libsec sys/src/libmp sys/src/cmd/mpc.y";
  };
  fortuneSource = exportSource "9front-fortune-source" {
    paths = "sys/src/cmd/fortune.c sys/src/libbio sys/games/lib/fortunes";
  };
  mkSource = exportSource "9front-mk-source" {
    paths = "sys/src/cmd/mk sys/src/libregexp";
  };
  yaccSource = exportSource "9front-yacc-source" {
    paths = "sys/src/cmd/yacc.c sys/lib/yaccpar sys/lib/yaccpars";
    check = ''
      test -s "$out/sys/src/cmd/yacc.c"
      test -s "$out/sys/lib/yaccpar"
      test -s "$out/sys/lib/yaccpars"
    '';
  };
  ccSource = exportSource "9front-cc-source" {
    paths = "sys/src/cmd/cc sys/src/cmd/6a sys/src/cmd/6c sys/src/cmd/6l sys/src/cmd/ar.c";
    check = ''
      for command in cc 6a 6c 6l; do
        test -s "$out/sys/src/cmd/$command/mkfile"
      done
    '';
  };
  patchSource = exportSource "9front-patch-source" {
    paths = "sys/src/cmd/patch.c sys/man/1/patch";
  };
  rcSource = exportSource "9front-rc-source" {
    paths = "sys/src/cmd/rc";
  };
  gitSource = exportSource "9front-git-source" {
    paths = "sys/src/cmd/git sys/src/libflate sys/man/1/git";
  };
  ramfsSource = exportSource "9front-ramfs-source" {
    paths = "sys/src/cmd/ramfs.c sys/man/4/ramfs sys/src/lib9p sys/src/libauth sys/src/libthread";
  };
  machSource = exportSource "9front-libmach-source" {
    paths = ''
      sys/src/libmach \
      sys/src/cmd/2c/2.out.h sys/src/cmd/5c/5.out.h sys/src/cmd/6c/6.out.h \
      sys/src/cmd/7c/7.out.h sys/src/cmd/8c/8.out.h sys/src/cmd/9c/9.out.h sys/src/cmd/kc/k.out.h \
      sys/src/cmd/qc/q.out.h sys/src/cmd/vc/v.out.h \
      386/include/ureg.h 68020/include/ureg.h amd64/include/ureg.h \
      arm/include/ureg.h arm64/include/ureg.h mips/include/ureg.h \
      power/include/ureg.h power64/include/ureg.h sparc/include/ureg.h sparc64/include/ureg.h'';
  };
  lexSource = exportSource "9front-lex-source" {
    paths = "sys/src/cmd/lex sys/src/ape/lib/l sys/include/ape/libl.h";
    check = ''
      test -s "$out/sys/src/cmd/lex/mkfile"
      test -s "$out/sys/src/cmd/lex/ncform"
      test -s "$out/sys/src/ape/lib/l/yywrap.c"
      test -s "$out/sys/include/ape/libl.h"
    '';
  };
}
