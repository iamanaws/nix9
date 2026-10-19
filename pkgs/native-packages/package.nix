{
  runCommand,
  nativeTools,
  secSource,
  fortuneSource,
  mkSource,
  sha1sum,
}:
runCommand "native-packages" { } ''
  mkdir -p "$out/pkgs"
  cp -r ${nativeTools} "$out/tools"
  cp -r ${secSource} "$out/libsec-source"
  cp -r ${fortuneSource} "$out/fortune-source"
  cp -r ${mkSource} "$out/mk-source"
  cp ${sha1sum.source} "$out/sha1sum.c"
  cp ${../../lib/mk-derivation.nix} "$out/mk-derivation.nix"
  cp ${../../lib/stdenv.nix} "$out/stdenv.nix"
  cp ${../../lib/setup-environment.nix} "$out/setup-environment.nix"
  cp ${../../lib/mk-shell.nix} "$out/mk-shell.nix"
  cp ${../../lib/build-env.nix} "$out/build-env.nix"
  cp ${../../lib/profile.rc} "$out/profile"
  cp ${../libsec/native.nix} "$out/pkgs/libsec.nix"
  cp ${../libmp/native.nix} "$out/pkgs/libmp.nix"
  cp ${../sha1sum/native.nix} "$out/pkgs/sha1sum.nix"
  cp ${../libbio/native.nix} "$out/pkgs/libbio.nix"
  cp ${../libregexp/native.nix} "$out/pkgs/libregexp.nix"
  cp ${../mk/native.nix} "$out/pkgs/mk.nix"
  cp ${../fortune/native.nix} "$out/pkgs/fortune.nix"
  cp ${../fetchurl/native.nix} "$out/pkgs/fetchurl.nix"
  cp ${../lua/native.nix} "$out/pkgs/lua.nix"
  cp ${../liblua/native.nix} "$out/pkgs/liblua.nix"
  cp ${../lua/source.nix} "$out/pkgs/lua-source.nix"
  cp ${../lua/ape-config.h} "$out/pkgs/lua-ape-config.h"
  cp ${./default.nix} "$out/default.nix"
''
