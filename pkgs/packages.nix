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
  libip = package ./libip { src = sources.ndbSource + "/sys/src/libip"; };
  libndb = package ./libndb { src = sources.ndbSource + "/sys/src/libndb"; };
  libauthsrv = package ./libauthsrv { src = sources.ndbSource + "/sys/src/libauthsrv"; };
  ndb = package ./ndb { src = sources.ndbSource + "/sys/src/cmd/ndb"; };
  auth = package ./auth { src = sources.accessSource + "/sys/src/cmd/auth"; };
  listen = package ./listen { src = sources.accessSource + "/sys/src/cmd/aux/listen.c"; };
  exportfs = package ./exportfs { src = sources.accessSource + "/sys/src/cmd/exportfs"; };
  rcpu = package ./rcpu { src = sources.accessSource; };
  namespaceTools = package ./namespace-tools { src = sources.accessSource; };
  dial = package ./dial { src = sources.accessSource + "/sys/src/cmd/aux/dial.c"; };
  libdisk = package ./libdisk { src = sources.storageSource + "/sys/src/libdisk"; };
  cwfs = package ./cwfs { src = sources.storageSource + "/sys/src/cmd/cwfs"; };
  diskArchive = package ./disk-archive { src = sources.storageSource; };
  lib9p = package ./lib9p { src = sources.ramfsSource + "/sys/src/lib9p"; };
  patch = package ./patch { src = sources.patchSource + "/sys/src/cmd/patch.c"; };
  ramfs = package ./ramfs { src = sources.ramfsSource + "/sys/src/cmd/ramfs.c"; };
  webfs = package ./webfs { src = sources.webfsSource + "/sys/src/cmd/webfs"; };
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
  libdraw = package ./libdraw { src = sources.graphicalSource + "/sys/src/libdraw"; };
  libframe = package ./libframe { src = sources.graphicalSource + "/sys/src/libframe"; };
  libplumb = package ./libplumb { src = sources.graphicalSource + "/sys/src/libplumb"; };
  libcomplete = package ./libcomplete { src = sources.graphicalSource + "/sys/src/libcomplete"; };
  fonts = package ./fonts { src = sources.graphicalSource + "/lib/font/bit/dejavu"; };
  rio = package ./rio { src = sources.graphicalSource; };
  plumber = package ./plumber { src = sources.graphicalSource; };
  acme = package ./acme { src = sources.graphicalSource; };
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
