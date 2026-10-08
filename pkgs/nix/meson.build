# Standalone legacy commands; the upstream CLI target includes unported commands.
command_deps = [dependency('boost')]
foreach part : ['util', 'store', 'fetchers', 'expr', 'main']
  command_deps += dependency('nix-' + part).partial_dependency(
    compile_args: true, includes: true,
  )
endforeach

foreach command : ['store', 'instantiate', 'build']
  sources = ['main.cc', 'src/nix/nix-' + command + '/nix-' + command + '.cc']
  args = []
  libraries = [nix_libraries['util'], nix_libraries['store'], nix_libraries['main']]
  if command == 'store'
    sources += ['src/nix/nix-store/dotgraph.cc', 'src/nix/nix-store/graphml.cc']
  else
    sources += ['src/libcmd/common-eval-args.cc']
    if command == 'build'
      sources += ['src/libcmd/network-proxy.cc']
      args += '-DNIX_BUILD'
    else
      args += '-DNIX_INSTANTIATE'
    endif
    libraries += [nix_libraries['fetchers'], nix_libraries['expr']]
  endif
  executable(
    'nix-' + command + '.elf', sources,
    dependencies: command_deps,
    include_directories: include_directories('src/libcmd/include', 'src/nix'),
    cpp_args: args,
    link_whole: libraries,
    link_args: ['-Wl,--wrap=__assert_fail'],
    override_options: ['cpp_std=c++23'],
  )
endforeach
