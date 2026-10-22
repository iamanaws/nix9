{ sources }:
let
  package = path: args: { inherit path args; };
  luaSource = import ./lua/source.nix;
in
{
  buildTools = package ./build-tools { src = sources.buildToolsSource; };
  libString = package ./libString { src = sources.buildToolsSource + "/sys/src/libString"; };
  awkMaketab = package ./awk-maketab { src = sources.buildToolsSource + "/sys/src/cmd/awk"; };
  libbio = package ./libbio { src = sources.fortuneSource + "/sys/src/libbio"; };
  libstdio = package ./libstdio { src = sources.ccSource + "/sys/src/libstdio"; };
  libregexp = package ./libregexp { src = sources.mkSource + "/sys/src/libregexp"; };
  mk = package ./mk { src = sources.mkSource + "/sys/src/cmd/mk"; };
  yacc = package ./yacc { src = sources.yaccSource; };
  rc = package ./rc { src = sources.rcSource + "/sys/src/cmd/rc"; };
  cc = package ./cc { src = sources.ccSource; };
  libmach = package ./libmach { src = sources.machSource; };
  ar = package ./ar { src = sources.ccSource + "/sys/src/cmd/ar.c"; };
  libflate = package ./libflate { src = sources.gitSource + "/sys/src/libflate"; };
  libauth = package ./libauth { src = sources.ramfsSource + "/sys/src/libauth"; };
  lib9p = package ./lib9p { src = sources.ramfsSource + "/sys/src/lib9p"; };
  patch = package ./patch { src = sources.patchSource + "/sys/src/cmd/patch.c"; };
  ramfs = package ./ramfs { src = sources.ramfsSource + "/sys/src/cmd/ramfs.c"; };
  fortune = package ./fortune { src = sources.fortuneSource; };
  git = package ./git {
    src = sources.gitSource + "/sys/src/cmd/git";
    exporter = ./git/export-tree.c;
  };
  lex = package ./lex { src = sources.lexSource + "/sys/src/cmd/lex"; };
  libl = package ./libl {
    src = sources.lexSource + "/sys/src/ape/lib/l";
    header = sources.lexSource + "/sys/include/ape/libl.h";
  };
  sha1sum = package ./sha1sum { src = sources.sha1sumSource; };
  libbsd = package ./libbsd { src = sources.apeSource; };
  libap = package ./libap { src = sources.apeSource; };
  libc = package ./libc { src = sources.apeSource + "/sys/src/libc"; };
  mpc = package ./mpc { src = sources.secSource; };
  libthread = package ./libthread { src = sources.ramfsSource + "/sys/src/libthread"; };
  clone = package ./clone { upstream = import ./clone/source.nix; };
  libmp = package ./libmp { src = sources.secSource; };
  libsec = package ./libsec { src = sources.secSource; };
  liblua = package ./liblua {
    upstream = luaSource;
    config = ./lua/ape-config.h;
  };
  lua = package ./lua { upstream = luaSource; };
  libbz2 = package ./libbz2 { };
}
