{ pkgs }:
let
  source = pkgs.fetchFromGitHub {
    owner = "9front";
    repo = "9front";
    # Release 11952, matching the test image.
    rev = "602faae9a52f342a40b086d10b23c71c82dd52d7";
    hash = "sha256-F1+LfWTR/vhYmvklSqfzgiORRpsw95aHKVlOD8xRI2A=";
  };
  unicodeTables = pkgs.callPackage ./libc/tables.nix { inherit source; };
  selectSource =
    name:
    {
      paths,
      postInstall ? "",
    }:
    pkgs.runCommand name { } (
      ''
        mkdir -p "$out"
        cd ${source}
        tar -cf - ${paths} | tar -xf - -C "$out"
      ''
      + postInstall
    );
in
{
  sha1sumSource = (pkgs.callPackage ./sha1sum/source.nix { }).source;
  sysroot = selectSource "9front-11952-amd64-sysroot" {
    paths = ''
      sys/include amd64/include amd64/mkfile \
      sys/src/mkfile.proto sys/src/cmd/mkone sys/src/cmd/mklib \
      sys/src/cmd/mkmany sys/src/cmd/mksyslib rc/lib/rcmain'';
    postInstall = ''
      test -s "$out/sys/include/libc.h"
      test -s "$out/amd64/include/u.h"
    '';
  };
  buildToolsSource = selectSource "build-tools-source" {
    paths =
      "sys/src/cmd/awk sys/src/cmd/grep sys/src/cmd/gzip sys/src/libString sys/src/libflate "
      + pkgs.lib.concatMapStringsSep " " (name: "sys/src/cmd/${name}.c") (
        import ./build-tools/commands.nix
      );
  };
  apeSource = selectSource "9front-ape-source" {
    paths = "sys/src/ape sys/src/libc";
    postInstall = ''
      chmod u+w "$out/sys/src/libc/ucd"
      cp ${unicodeTables}/* "$out/sys/src/libc/ucd/"
    '';
  };
  secSource = selectSource "9front-libsec-source" {
    paths = "sys/src/libsec sys/src/libmp sys/src/cmd/mpc.y";
  };
  fortuneSource = selectSource "9front-fortune-source" {
    paths = "sys/src/cmd/fortune.c sys/src/libbio sys/games/lib/fortunes";
  };
  mkSource = selectSource "9front-mk-source" {
    paths = "sys/src/cmd/mk sys/src/libregexp";
  };
  yaccSource = selectSource "9front-yacc-source" {
    paths = "sys/src/cmd/yacc.c sys/lib/yaccpar sys/lib/yaccpars";
    postInstall = ''
      test -s "$out/sys/src/cmd/yacc.c"
      test -s "$out/sys/lib/yaccpar"
      test -s "$out/sys/lib/yaccpars"
    '';
  };
  ccSource = selectSource "9front-cc-source" {
    paths = "sys/src/cmd/cc sys/src/cmd/6a sys/src/cmd/6c sys/src/cmd/6l sys/src/cmd/cpp sys/src/cmd/pcc.c sys/src/cmd/ar.c sys/src/libstdio";
    postInstall = ''
      for command in cc 6a 6c 6l cpp; do
        test -s "$out/sys/src/cmd/$command/mkfile"
      done
    '';
  };
  patchSource = selectSource "9front-patch-source" {
    paths = "sys/src/cmd/patch.c sys/man/1/patch";
  };
  rcSource = selectSource "9front-rc-source" {
    paths = "sys/src/cmd/rc";
  };
  gitSource = selectSource "9front-git-source" {
    paths = "sys/src/cmd/git sys/src/libflate sys/man/1/git";
  };
  ramfsSource = selectSource "9front-ramfs-source" {
    paths = "sys/src/cmd/ramfs.c sys/man/4/ramfs sys/src/lib9p sys/src/libauth sys/src/libthread";
  };
  ndbSource = selectSource "9front-ndb-source" {
    paths = "sys/src/libip sys/src/libndb sys/src/libauthsrv sys/src/cmd/ndb";
  };
  webfsSource = selectSource "9front-webfs-source" {
    paths = "sys/src/cmd/webfs";
  };
  machSource = selectSource "9front-libmach-source" {
    paths = ''
      sys/src/libmach \
      sys/src/cmd/2c/2.out.h sys/src/cmd/5c/5.out.h sys/src/cmd/6c/6.out.h \
      sys/src/cmd/7c/7.out.h sys/src/cmd/8c/8.out.h sys/src/cmd/9c/9.out.h sys/src/cmd/kc/k.out.h \
      sys/src/cmd/qc/q.out.h sys/src/cmd/vc/v.out.h \
      386/include/ureg.h 68020/include/ureg.h amd64/include/ureg.h \
      arm/include/ureg.h arm64/include/ureg.h mips/include/ureg.h \
      power/include/ureg.h power64/include/ureg.h sparc/include/ureg.h sparc64/include/ureg.h'';
  };
  lexSource = selectSource "9front-lex-source" {
    paths = "sys/src/cmd/lex sys/src/ape/lib/l sys/include/ape/libl.h";
    postInstall = ''
      test -s "$out/sys/src/cmd/lex/mkfile"
      test -s "$out/sys/src/cmd/lex/ncform"
      test -s "$out/sys/src/ape/lib/l/yywrap.c"
      test -s "$out/sys/include/ape/libl.h"
    '';
  };
}
