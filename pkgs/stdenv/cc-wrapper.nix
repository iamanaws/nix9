{
  lib,
  runCommand,
  cTools,
  sysroot,
  shell,
  gcc,
  pcc,
}:
runCommand "plan9-cross-cc" { } ''
  mkdir -p "$out/bin"
  ${lib.concatMapStringsSep "\n"
    (tool: ''
        cat > "$out/bin/${tool}" <<'EOF'
      #!${shell}
      flags=()
      root=${sysroot}
      if(! ~ $#NIX9_ROOT 0) root=$NIX9_ROOT
      for(directory in $NIX9_INCLUDE_DIRS) flags=($flags -I $directory)
      exec ${cTools}/bin/${tool} ${
        lib.optionalString (tool == "6c") "-B '-D_Noreturn='"
      } $flags -I $root/amd64/include -I $root/sys/include $*
      EOF
    '')
    [
      "6c"
      "6a"
    ]
  }
  cat > "$out/bin/6l" <<'EOF'
  #!${shell}
  flags=()
  for(directory in $NIX9_LIBRARY_DIRS) flags=($flags -L $directory)
  exec ${cTools}/bin/6l -H2 $flags $*
  EOF
  cat > "$out/bin/ar" <<'EOF'
  #!${shell}
  if(~ $#* 0) exec ${cTools}/bin/9ar
  exec ${cTools}/bin/9ar $1^D $*(2-)
  EOF
  chmod +x "$out/bin/ar"
  ln -s ${pcc}/bin/pcc "$out/bin/pcc"
  cat > "$out/bin/cpp" <<'EOF'
  #!${shell}
  flags=(-E -P -undef -nostdinc '-D_Noreturn=' -std=c99)
  for(directory in $NIX9_APE_INCLUDE_DIRS) flags=($flags -I $directory)
  files=()
  for(arg in $*) {
    switch($arg) {
    case -N '-D__STDC__=1'
    case -*
      flags=($flags $arg)
    case *
      files=($files $arg)
    }
  }
  if(~ $#files 2) exec ${gcc}/bin/gcc $flags $files(1) -o $files(2)
  exec ${gcc}/bin/gcc $flags $files
  EOF
  chmod +x "$out/bin/cpp"
  chmod +x "$out/bin/6c" "$out/bin/6a" "$out/bin/6l"
''
