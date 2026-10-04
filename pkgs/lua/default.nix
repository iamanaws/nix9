{
  runCommand,
  lib,
  fetchurl,
  gcc,
  go,
  cTools,
  sysroot,
  libbsd,
  libap,
}:
let
  upstream = import ./source.nix;
  inherit (upstream) version;
  guestPrefix = "/usr/local/pkg/lua-${version}";
  archive = fetchurl upstream.src;
  # Both compilers use the same sources and APE configuration.
  source = runCommand "lua-${version}-ape.tar.gz" { } ''
    tar -xzf ${archive}
    cp ${./ape-config.h} lua-${version}/src/ape-config.h
    substituteInPlace lua-${version}/src/ape-config.h \
      --replace-fail '@guestPrefix@' '${guestPrefix}'
    sed -i '1i#include "ape-config.h"' lua-${version}/src/lprefix.h
    tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
      -czf "$out" lua-${version}
  '';
in
runCommand "lua-${version}-9front"
  {
    nativeBuildInputs = [
      gcc
      go
      cTools
    ];
    ccroot = sysroot;
    apeBsdLibrary = "${libbsd}/lib/libbsd.a";
    apeCoreLibrary = "${libap}/lib/libap.a";
    passthru = {
      inherit
        source
        archive
        version
        guestPrefix
        ;
    };
    meta = {
      description = "Lua interpreter for 9front using APE";
      homepage = "https://www.lua.org";
      license = lib.licenses.mit;
    };
  }
  ''
    tar -xzf ${source}
    cd lua-${version}/src
    source ${../../lib/ape-build.sh}
    for source in *.c; do
      if [ "$source" = luac.c ]; then continue; fi
      unit="''${source%.c}"
      apeCompile "$source" "$unit.6" c89
    done
    apeLink lua *.6
    export HOME="$TMPDIR" GOCACHE="$TMPDIR/go-cache" GOPROXY=off GOTOOLCHAIN=local
    go run ${../../tests/format.go} lua
    install -Dm755 lua "$out/bin/lua"
    mkdir -p "$out/share/lua/5.4"
    install -Dm644 ../doc/readme.html "$out/share/doc/lua/readme.html"
  ''
