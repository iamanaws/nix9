# The caller sets runtime to the cc9 target runtime directory.
cc9Flags=(
  --target=x86_64-unknown-none -D__plan9__ -fno-pic
  -ffunction-sections -fdata-sections
  -isystem "$runtime/sysinc/cc9"
)
cc9CxxFlags=(
  -isystem "$runtime/sysinc/cxxv1" "${cc9Flags[@]}"
  -std=c++23 -nostdinc++ -nostdlib -femulated-tls
  -D_LIBCPP_PROVIDES_DEFAULT_RUNE_TABLE -D_LIBCPP_HAS_CLOCK_GETTIME
)
