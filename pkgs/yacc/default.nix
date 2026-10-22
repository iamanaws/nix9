{
  mkPlan9Program,
  libbio,
  source,
}:
(mkPlan9Program {
  name = "yacc";
  sources = [ "${source}/sys/src/cmd/yacc.c" ];
  libraries = [ libbio ];
}).overrideAttrs
  (old: {
    buildCommand = old.buildCommand + ''
      mkdir -p "$out/share/yacc"
      cp ${source}/sys/lib/yaccpar ${source}/sys/lib/yaccpars "$out/share/yacc/"
    '';
  })
