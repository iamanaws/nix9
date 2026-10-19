{
  runCommand,
  nativeTools,
  secSource,
  fortuneSource,
  sha1sum,
}:
runCommand "native-packages" { } ''
  mkdir -p "$out/pkgs"
  cp -r ${nativeTools} "$out/tools"
  cp -r ${secSource} "$out/libsec-source"
  cp -r ${fortuneSource} "$out/fortune-source"
  cp ${sha1sum.source} "$out/sha1sum.c"
  cp ${../../lib/mk-derivation.nix} "$out/mk-derivation.nix"
  cp ${../../lib/build-env.nix} "$out/build-env.nix"
  cp ${../libsec/native.nix} "$out/pkgs/libsec.nix"
  cp ${../sha1sum/native.nix} "$out/pkgs/sha1sum.nix"
  cp ${../libbio/native.nix} "$out/pkgs/libbio.nix"
  cp ${../fortune/native.nix} "$out/pkgs/fortune.nix"
  cp ${../fetchurl/native.nix} "$out/pkgs/fetchurl.nix"
  cp ${../lua/native.nix} "$out/pkgs/lua.nix"
  cp ${../liblua/native.nix} "$out/pkgs/liblua.nix"
  cp ${../lua/source.nix} "$out/pkgs/lua-source.nix"
  cp ${../lua/ape-config.h} "$out/pkgs/lua-ape-config.h"
  cp ${./default.nix} "$out/default.nix"
''
