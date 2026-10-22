{ mkPlan9Library, source }:
mkPlan9Library {
  name = "libstdio";
  src = "${source}/sys/src/libstdio";
}
