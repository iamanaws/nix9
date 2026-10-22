{
  fetchgit,
  applyPatches,
  mkPlan9Program,
  libthread,
}:
let
  src = applyPatches {
    src = fetchgit (import ./source.nix);
    patches = [ ./directories-only.patch ];
  };
in
(mkPlan9Program {
  name = "clone";
  sources = [ "${src}/clone.c" ];
  libraries = [ libthread ];
  meta.description = "Parallel file and directory copying";
}).overrideAttrs
  (old: {
    buildCommand = old.buildCommand + ''
      install -Dm644 ${src}/clone.man "$out/man/1/clone"
      install -Dm644 ${src}/LICENSE "$out/share/doc/clone/LICENSE"
    '';
  })
