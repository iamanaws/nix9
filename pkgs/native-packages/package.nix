{
  runCommand,
  nativeTools,
  buildToolsSource,
  ccSource,
  libcSource,
  secSource,
  fortuneSource,
  mkSource,
  yaccSource,
  lexSource,
  rcSource,
  machSource,
  ramfsSource,
  gitSource,
  patchSource,
  sha1sum,
}:
runCommand "native-packages" { } ''
  mkdir -p "$out/pkgs" "$out/bin"
  cp -r ${nativeTools} "$out/tools"
  cp -r ${buildToolsSource} "$out/build-tools-source"
  mkdir "$out/pkgs/build-tools"
  cp ${../build-tools/native.nix} "$out/pkgs/build-tools/native.nix"
  cp ${../build-tools/commands.nix} "$out/pkgs/build-tools/commands.nix"
  cp -r ${ccSource} "$out/cc-source"
  cp ${ccSource}/sys/src/cmd/ar.c "$out/ar.c"
  cp ${patchSource}/sys/src/cmd/patch.c "$out/patch.c"
  cp -r ${libcSource}/sys/src/libc "$out/libc-source"
  cp -r ${secSource} "$out/libsec-source"
  cp -r ${fortuneSource} "$out/fortune-source"
  cp -r ${mkSource} "$out/mk-source"
  cp -r ${yaccSource} "$out/yacc-source"
  cp -r ${lexSource} "$out/lex-source"
  cp -r ${rcSource}/sys/src/cmd/rc "$out/rc-source"
  cp -r ${gitSource} "$out/git-source"
  cp -r ${ramfsSource} "$out/ramfs-source"
  cp -r ${machSource} "$out/libmach-source"
  cp ${sha1sum.source} "$out/sha1sum.c"
  cp ${../../lib/mk-derivation.nix} "$out/mk-derivation.nix"
  cp ${../../lib/call-package.nix} "$out/call-package.nix"
  cp ${../../lib/stdenv.nix} "$out/stdenv.nix"
  cp ${../../lib/setup-environment.nix} "$out/setup-environment.nix"
  cp ${../../lib/mk-shell.nix} "$out/mk-shell.nix"
  cp ${../../lib/build-env.nix} "$out/build-env.nix"
  cp ${../../lib/profile.rc} "$out/profile"
  cp ${../../lib/nix-profile.rc} "$out/bin/nix-profile"
  chmod +x "$out/bin/nix-profile"
  cp ${../libsec/native.nix} "$out/pkgs/libsec.nix"
  cp ${../libmp/native.nix} "$out/pkgs/libmp.nix"
  cp ${../sha1sum/native.nix} "$out/pkgs/sha1sum.nix"
  cp ${../libmach/native.nix} "$out/pkgs/libmach.nix"
  cp ${../libflate/native.nix} "$out/pkgs/libflate.nix"
  cp ${../git/native.nix} "$out/pkgs/git.nix"
  cp ${../git/export-tree.c} "$out/pkgs/git-export-tree.c"
  cp ${../fetchgit/native.nix} "$out/pkgs/fetchgit.nix"
  cp ${../clone/native.nix} "$out/pkgs/clone.nix"
  cp ${../clone/source.nix} "$out/pkgs/clone-source.nix"
  cp ${../clone/directories-only.patch} "$out/pkgs/directories-only.patch"
  cp ${../lib9p/native.nix} "$out/pkgs/lib9p.nix"
  cp ${../libauth/native.nix} "$out/pkgs/libauth.nix"
  cp ${../libthread/native.nix} "$out/pkgs/libthread.nix"
  cp ${../ramfs/native.nix} "$out/pkgs/ramfs.nix"
  cp ${../libbio/native.nix} "$out/pkgs/libbio.nix"
  cp ${../libc/native.nix} "$out/pkgs/libc.nix"
  cp ${../cc/native.nix} "$out/pkgs/cc.nix"
  cp ${../ar/native.nix} "$out/pkgs/ar.nix"
  cp ${../ar/source-date-epoch.patch} "$out/pkgs/source-date-epoch.patch"
  cp ${../patch/native.nix} "$out/pkgs/patch.nix"
  cp ${../libregexp/native.nix} "$out/pkgs/libregexp.nix"
  cp ${../mk/native.nix} "$out/pkgs/mk.nix"
  cp ${../rc/native.nix} "$out/pkgs/rc.nix"
  cp ${../yacc/native.nix} "$out/pkgs/yacc.nix"
  cp ${../lex/native.nix} "$out/pkgs/lex.nix"
  cp ${../libl/native.nix} "$out/pkgs/libl.nix"
  cp ${../fortune/native.nix} "$out/pkgs/fortune.nix"
  cp ${../fetchurl/native.nix} "$out/pkgs/fetchurl.nix"
  cp ${../lua/native.nix} "$out/pkgs/lua.nix"
  cp ${../liblua/native.nix} "$out/pkgs/liblua.nix"
  cp ${../lua/source.nix} "$out/pkgs/lua-source.nix"
  cp ${../lua/ape-config.h} "$out/pkgs/lua-ape-config.h"
  cp ${./default.nix} "$out/default.nix"
  cp ${./bootstrap.nix} "$out/bootstrap.nix"
''
