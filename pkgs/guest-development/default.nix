{
  runCommand,
  cc,
  sysroot,
  libc,
  libap,
  libbsd,
}:
let
  guestPrefix = "/usr/local/pkg/c-development-11952";
in
runCommand "9front-c-development" { passthru = { inherit guestPrefix; }; } ''
  mkdir -p "$out/bin" "$out/libexec" "$out/sys" "$out/amd64/lib"
  cp ${cc}/bin/* "$out/libexec/"
  cp -r ${sysroot}/sys/include "$out/sys/"
  cp -r ${sysroot}/amd64/include "$out/amd64/"
  cp ${libc}/lib/libc.a "$out/amd64/lib/"
  mkdir -p "$out/amd64/lib/ape"
  cp ${libap}/lib/libap.a ${libbsd}/lib/libbsd.a "$out/amd64/lib/ape/"
  cat > "$out/bin/6c" <<'EOF'
  #!/bin/rc
  exec ${guestPrefix}/libexec/6c -I ${guestPrefix}/amd64/include -I ${guestPrefix}/sys/include $*
  EOF
  cat > "$out/bin/6l" <<'EOF'
  #!/bin/rc
  exec ${guestPrefix}/libexec/6l -l -E _main $* ${guestPrefix}/amd64/lib/libc.a
  EOF
  cat > "$out/bin/pcc" <<'EOF'
  #!/bin/rc
  rfork n || exit $status
  bind ${guestPrefix}/sys/include /sys/include || exit $status
  bind ${guestPrefix}/amd64/include /amd64/include || exit $status
  bind ${guestPrefix}/amd64/lib /amd64/lib || exit $status
  bind -b ${guestPrefix}/libexec /bin || exit $status
  exec ${guestPrefix}/libexec/pcc $*
  EOF
  chmod +x "$out/bin/6c" "$out/bin/6l" "$out/bin/pcc"
''
