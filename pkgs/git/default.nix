{
  mkDerivation,
  src,
  exporter,
  libbio,
  libmp,
  libsec,
  libflate,
  libregexp,
}:
mkDerivation {
  name = "git";
  inherit src;
  buildInputs = [
    libbio
    libmp
    libsec
    libflate
    libregexp
  ];
  postUnpack = "cp ${exporter} export-tree.c";
  buildFlags = [
    "6.get"
    "6.export-tree"
  ];
  installPhase = ''
    mkdir -p $out/bin/git
    for(command in get export-tree) cp 6.$command $out/bin/git/$command
  '';
  meta.description = "Native Git transport and source export tools";
}
