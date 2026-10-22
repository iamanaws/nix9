{ mkPlan9Library, source }:
mkPlan9Library {
  name = "libthread";
  src = "${source}/sys/src/libthread";
  # goken9cc lacks _Noreturn; -B permits paths ending in abort().
  cFlags = [ "-B" ];
}
