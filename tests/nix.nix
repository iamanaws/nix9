{
  pkgs,
  lua,
  nativePackages,
  nativePackagesArchive,
  nativeTools,
  nixPackage,
  nixProbe,
  nixUtil,
  python,
  testSupport,
  vm,
  vmTest,
}:
rec {
  cc9-tests = pkgs.runCommand "cc9-tests" { requiredSystemFeatures = [ "kvm" ]; } ''
    export CXX=${pkgs.llvmPackages_22.clang-unwrapped}/bin/clang++
    export LD=${pkgs.llvmPackages_22.lld}/bin/ld.lld
    export PYTHON=${python}/bin/python
    bash ${./cc9}/build.sh ${nixUtil.cc9} ${nixUtil.cc9.elf2aout} "$out"
    ${python}/bin/python ${testSupport [ ./smoke.py ]}/smoke.py \
      ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
      "$out/runtime-tests" 'cc9 runtime tests PASS'
    echo '{"runtime": "passed"}' > "$out/results.json"
  '';
  nix-core-tests = vmTest "nix-core-tests" {
    script = ./libutil.py;
    files = [
      ./nix_store.py
      ./nix_eval.py
      ./nix_build.py
      ./nix_build_cli.py
      ./nix_repair.py
      ./nix-build.nix
      ./nix_concurrency.py
      ./concurrent-builds.nix
      ./c_abi.py
      ./sha1sum.py
      ./libutil_compression.py
      ./libutil_keys.py
      ./artifacts.py
    ];
    nativeBuildInputs = [
      pkgs.nix
      pkgs.brotli
      pkgs.zstd
      pkgs.openssl
    ];
    env.SODIUM_LIBRARY = "${pkgs.libsodium}/lib/libsodium.so";
    args = ''
      ${nixUtil.cc9.elf2aout} ${nixProbe}/probe.elf ${nixUtil}/nix-store.elf ${nixUtil}/nix-instantiate.elf ${nixUtil}/nix-build.elf \
      ${../pkgs/hello-c-cross} ${./c-abi} ${nativePackages} ${nativeTools} "$out"
    '';
  };
  nix-native-tests = vmTest "nix-native-tests" {
    script = ./native_install.py;
    files = [
      ./native_fetch.py
      ./eval_fetch.py
      ./tls.py
      ./eval_tarball.py
      ./native_sources.py
      ./native_fortune.py
      ./cache_publish.py
      ./libsec.py
      ./libsec/native.nix
      ./libsec/mp.c
      ./libsec/generated.sha256
      ./native_project.py
      ./native_yacc.py
      ./yacc.nix
      ./yacc
      ./native_lex.py
      ./lex.nix
      ./lex
      ./native_libc.py
      ./libc.nix
      ./libc.c
      ./native_cc.py
      ./cc.nix
      ./native_phases.py
      ./phases.nix
      ./mk-phases.nix
      ./overrides.nix
      ./native_inputs.py
      ./inputs.nix
      ./native_environments.py
      ./environments.nix
      ./native_recovery.py
      ./artifacts.py
      ./recovery.nix
      ./sources.nix
      ./isolation.nix
      ./lua.py
      ./lua
      ./fetch.nix
    ];
    nativeBuildInputs = [
      pkgs.nix
      pkgs.openssl
    ];
    preRun = ''
      mkdir -p "$out"
    '';
    args = ''
      ${nixPackage} ${nixPackage.guestPrefix} \
      ${nativePackagesArchive} ${nativePackagesArchive.guestPrefix} "$out" ${lua.archive} \
      ${nixProbe}/probe.elf ${nixUtil.cc9.elf2aout} ${../examples/hello}
    '';
  };
  nix-fetch-tests = vmTest "nix-fetch-tests" {
    script = ./eval_fetch.py;
    files = [
      ./eval_tarball.py
      ./tls.py
    ];
    nativeBuildInputs = [
      pkgs.nix
      pkgs.openssl
    ];
    args = ''
      ${nixPackage} ${nixPackage.guestPrefix} "$out"
    '';
  };
  nix-store-tests = vmTest "nix-store-tests" {
    script = ./native_store.py;
    files = [
      ./cache_publish.py
      ./native_transfer.py
      ./native_cache.py
      ./native_cache_network.py
      ./native_cache_http.py
      ./tls.py
      ./artifacts.py
    ];
    nativeBuildInputs = [ pkgs.nix ];
    preRun = ''
      mkdir -p "$out"
    '';
    args = ''
      ${nixPackage} ${nixPackage.guestPrefix} ${nix-native-tests}/closure \
      ${nixProbe}/probe.elf ${nixUtil.cc9.elf2aout} "$out"
    '';
  };
  nix-util-tests = pkgs.runCommand "nix-util-tests" { } ''
    mkdir -p "$out"
    cp ${nix-core-tests}/results.json ${nix-native-tests}/native-install.json ${nix-store-tests}/native-store.json "$out/"
    cp ${nix-fetch-tests}/results.json "$out/fetch.json"
  '';
}
