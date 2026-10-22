{
  stdenv,
  fetchgit,
  libthread,
  upstream,
}:
stdenv.mkDerivation {
  name = "clone";
  src = fetchgit upstream;
  patches = [ ./directories-only.patch ];
  buildInputs = [ libthread ];
  installPhase = ''
    mkdir -p $out/bin $out/man/1
    mk 'BIN='$out/bin 'MAN='$out/man/1 install
  '';
  postInstall = ''
    mkdir -p $out/share/doc/clone
    cp LICENSE $out/share/doc/clone/
  '';
  meta.description = "Parallel file and directory copying";
}
