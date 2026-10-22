{
  applyPatches,
  mkPlan9Program,
  libmach,
  libbio,
  source,
}:
let
  src = applyPatches {
    name = "ar-source";
    src = "${source}/sys/src/cmd";
    patches = [ ./source-date-epoch.patch ];
  };
in
mkPlan9Program {
  name = "ar";
  cFlags = [ "-B" ]; # armalloc ends in sysfatal, which this compiler treats as returning.
  sources = [ "${src}/ar.c" ];
  libraries = [
    libmach
    libbio
  ];
}
