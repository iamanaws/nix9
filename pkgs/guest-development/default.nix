{
  runCommand,
  sysroot,
  libc,
}:
let
  guestPrefix = "/usr/local/pkg/c-development-11952";
in
runCommand "9front-c-development" { passthru = { inherit guestPrefix; }; } ''
  mkdir -p "$out/bin" "$out/sys" "$out/amd64/lib"
  cp -r ${sysroot}/sys/include "$out/sys/"
  cp -r ${sysroot}/amd64/include "$out/amd64/"
  cp ${libc}/lib/libc.a "$out/amd64/lib/"
  cat > "$out/bin/6c" <<'EOF'
  #!/bin/rc
  exec /amd64/bin/6c -I ${guestPrefix}/amd64/include -I ${guestPrefix}/sys/include $*
  EOF
  cat > "$out/bin/6l" <<'EOF'
  #!/bin/rc
  exec /amd64/bin/6l -l -E _main $* ${guestPrefix}/amd64/lib/libc.a
  EOF
  chmod +x "$out/bin/6c" "$out/bin/6l"
''
