project('nix9-commands', 'cpp')

# Standalone legacy commands; the upstream CLI target includes unported commands.
nix_libraries = {}
foreach part : ['util', 'store', 'fetchers', 'expr', 'main']
  nix_libraries += {part: dependency('nix-' + part, static: true)}
endforeach
command_deps = [nix_libraries['main']]

foreach command : ['store', 'instantiate', 'build', 'build-remote']
  sources = ['main.cc']
  if command == 'build-remote'
    sources += ['src/nix/build-remote/build-remote.cc']
  else
    sources += ['src/nix/nix-' + command + '/nix-' + command + '.cc']
  endif
  args = []
  libraries = ['util', 'store', 'main']
  if command == 'store'
    sources += ['src/nix/nix-store/dotgraph.cc', 'src/nix/nix-store/graphml.cc']
  elif command == 'build-remote'
    args += '-DNIX_BUILD_REMOTE'
  else
    sources += ['src/libcmd/common-eval-args.cc']
    if command == 'build'
      sources += ['src/libcmd/network-proxy.cc', 'shell.cc']
      args += '-DNIX_BUILD'
    else
      args += '-DNIX_INSTANTIATE'
    endif
    libraries += ['fetchers', 'expr']
  endif
  # Keep static initializers when linking the separately built archives.
  link_args = ['-Wl,--whole-archive']
  foreach part : libraries
    link_args += nix_libraries[part].get_variable(pkgconfig: 'libdir') / ('libnix' + part + '.a')
  endforeach
  link_args += ['-Wl,--no-whole-archive', '-Wl,--wrap=__assert_fail']
  executable(
    'nix-' + command + '.elf', sources,
    dependencies: command_deps,
    include_directories: include_directories('src/libcmd/include', 'src/nix'),
    cpp_args: args,
    link_args: link_args,
    override_options: ['cpp_std=c++23'],
  )
endforeach
