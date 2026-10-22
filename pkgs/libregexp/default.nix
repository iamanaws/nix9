{ mkPlan9Library, source }:
mkPlan9Library {
  name = "libregexp";
  src = "${source}/sys/src/libregexp";
  cFlags = [ "-B" ];
}
