{
  pkgs,
  ar,
  cc,
  cloneRepository,
  compressedText,
  libmach,
  mk,
  nativeBootstrap,
  nativeGoBootstrap,
  nativePackageSource,
  nativePackagesArchive,
  nixPackage,
  python,
  rc,
  testSupport,
  vm,
  webfs,
  vmTest,
}:
{
  native-netroot-tests = vmTest "native-netroot-tests" {
    nativeBuildInputs = [
      pkgs.netcat-openbsd
      pkgs.mtools
    ];
    script = ./native_netroot.py;
    files = [
      ./netroot.nix
      ./netroot-project.nix
      ./machine-newns.c
      ./boot_medium.py
    ];
    env.NIX9_NETROOT_TEST_STATE = "netroot-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-graphical-tests = vmTest "native-graphical-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_graphical.py;
    files = [ ./graphical.nix ];
    env.NIX9_GRAPHICAL_TEST_STATE = "graphical-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-builder-tests = vmTest "native-builder-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_builders.py;
    files = [
      ./builders.nix
      ./remote-project.nix
      ./remote-delay.c
    ];
    env.NIX9_BUILDER_TEST_STATE = "builder-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-backup-tests = vmTest "native-backup-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_storage.py;
    files = [
      ./backups.nix
      ./native_backups.py
    ];
    env = {
      NIX9_STORAGE_TEST_STATE = "backup-state";
      NIX9_BACKUP_TEST = "1";
    };
    args = "${nativeBootstrap} \"$out\"";
  };
  native-storage-tests = vmTest "native-storage-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_storage.py;
    files = [ ./storage.nix ];
    env.NIX9_STORAGE_TEST_STATE = "storage-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-network-server-tests = vmTest "native-network-server-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_network_server.py;
    files = [ ./network-server.nix ];
    env.NIX9_NETWORK_SERVER_TEST_STATE = "network-server-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-binding-tests = vmTest "native-binding-tests" {
    script = ./native_bindings.py;
    files = [
      ./bindings.nix
      ./binding-checks.nix
      ./binding-helper.rc
      ./binding-failed-refresh.rc
    ];
    args = "${nativeBootstrap} \"$out\"";
  };
  native-deployment-tests = vmTest "native-deployment-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_deployment.py;
    files = [
      ./deployment.nix
      ./deployment-truncate.rc
      ./deployment-store.rc
      ./deployment-stop.rc
      ./deployment-target.rc
      ./artifacts.py
    ];
    env.NIX9_DEPLOYMENT_TEST_STATE = "deployment-state";
    args = "${nativeBootstrap} \"$out\"";
  };
  native-job-tests = vmTest "native-job-tests" {
    script = ./native_jobs.py;
    files = [
      ./jobs.nix
      ./job-checks.nix
    ];
    args = "${nativeBootstrap} \"$out\"";
  };
  native-directory-tests = vmTest "native-directory-tests" {
    script = ./native_directories.py;
    files = [
      ./directories.nix
      ./directory-checks.nix
      ./directory-mounted.rc
    ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-prebuilt-tests = vmTest "native-prebuilt-tests" {
    script = ./native_prebuilt.py;
    files = [
      ./prebuilt.nix
      ./artifacts.py
    ];
    env.NIX9_PREBUILT_TEST_STATE = "prebuilt-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-sharing-tests = vmTest "native-sharing-tests" {
    nativeBuildInputs = [ pkgs.netcat-openbsd ];
    script = ./native_sharing.py;
    files = [
      ./sharing.nix
      ./installation.nix
      ./installation-checks.nix
      ./sharing-project
      ./sharing-failed-refresh.rc
      ./binding-failed-refresh.rc
      ./machine-newns.c
    ];
    env.NIX9_SHARING_TEST_STATE = "sharing-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-ndb-tests = vmTest "native-ndb-tests" {
    script = ./native_ndb.py;
    files = [ ./ndb.nix ];
    env.NIX9_NDB_TEST_STATE = "ndb-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-machine-tests = vmTest "native-machine-tests" {
    script = ./native_machine.py;
    files = [
      ./machines.nix
      ./machine-newns.c
    ];
    env.NIX9_MACHINE_TEST_STATE = "machine-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-module-tests = vmTest "native-module-tests" {
    script = ./native_modules.py;
    files = [
      ./modules.nix
      ./module-import.nix
      ./module-system.nix
      ./module-probe.rc
    ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-rcpu-tests = vmTest "native-rcpu-tests" {
    script = ./native_rcpu.py;
    files = [
      ./rcpu.nix
      ./access.nix
      ./rcpu-project
    ];
    env.NIX9_RCPU_TEST_STATE = "rcpu-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-listen-tests = vmTest "native-listen-tests" {
    script = ./native_listen.py;
    files = [ ./listen.nix ];
    env.NIX9_LISTEN_TEST_STATE = "listen-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-cpu-tests = vmTest "native-cpu-tests" {
    script = ./native_cpu.py;
    files = [
      ./cpu.nix
      ./ntp.py
    ];
    env.NIX9_CPU_TEST_STATE = "cpu-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-logging-tests = vmTest "native-logging-tests" {
    script = ./native_logging.py;
    files = [ ./logging.nix ];
    env.NIX9_LOGGING_TEST_STATE = "logging-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-timesync-tests = vmTest "native-timesync-tests" {
    script = ./native_timesync.py;
    files = [
      ./timesync.nix
      ./ntp.py
    ];
    env.NIX9_TIMESYNC_TEST_STATE = "timesync-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-services-tests = vmTest "native-services-tests" {
    script = ./native_services.py;
    files = [
      ./services.nix
      ./services-retained.rc
      ./tls.py
      ./webfs_tls.py
    ];
    nativeBuildInputs = [ pkgs.openssl ];
    # Retain the VM inside a --keep-failed build directory for diagnosis.
    env.NIX9_SERVICES_TEST_STATE = "services-state";
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-network-tests = vmTest "native-network-tests" {
    script = ./native_network.py;
    files = [ ./networks.nix ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-system-tests = vmTest "native-system-tests" {
    script = ./native_system.py;
    files = [ ./systems.nix ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-go-tests = vmTest "native-go-tests" {
    script = ./native_go.py;
    files = [
      ./go.nix
      ./go
      ./go-vendor
      ./artifacts.py
    ];
    args = ''
      ${nativeGoBootstrap} "$out"
    '';
  };
  webfs-tests = vmTest "webfs-tests" {
    script = ./webfs.py;
    files = [
      ./webfs.nix
      ./eval_fetch.py
      ./tls.py
      ./webfs_tls.py
      ./eval_tarball.py
      ./native_cache.py
      ./native_cache_http.py
      ./cache_publish.py
      ./artifacts.py
    ];
    nativeBuildInputs = [
      pkgs.nix
      pkgs.openssl
    ];
    args = ''
      ${nixPackage} ${nixPackage.guestPrefix} \
      ${nativePackagesArchive} ${nativePackagesArchive.guestPrefix} ${webfs} "$out"
    '';
  };
  native-bootstrap-tests = vmTest "native-bootstrap-tests" {
    script = ./native_bootstrap.py;
    files = [
      ./rc.nix
      ./bootstrap-inputs.nix
      ./cc.nix
      ./libc.c
      ./libsec/native.nix
      ./libsec/mp.c
      ./libsec/generated.sha256
      ./build-tools.nix
      ./build-tools.rc
      ./mk-phases.nix
      ./inputs.nix
    ];
    args = ''
      ${nativeBootstrap} \
      ${mk}/bin/mk ${rc}/bin/rc ${cc} ${ar}/bin/ar ${libmach}/lib/libmach.a ${compressedText} "$out"
    '';
  };
  native-shell-tests = vmTest "native-shell-tests" {
    script = ./native_shell.py;
    files = [
      ./native_inputs.py
      ./inputs.nix
      ./pure-shell.rc
    ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-patch-tests = vmTest "native-patch-tests" {
    script = ./native_patches.py;
    files = [ ./patches.nix ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-ramfs-tests = vmTest "native-ramfs-tests" {
    script = ./native_ramfs.py;
    files = [ ./sessions.nix ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-git-tests = vmTest "native-git-tests" {
    script = ./native_git.py;
    files = [ ./git.nix ];
    nativeBuildInputs = [
      pkgs.git
      pkgs.nix
    ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  native-clone-tests = vmTest "native-clone-tests" {
    script = ./native_clone.py;
    files = [
      ./clone.nix
      ./clone.py
      ./clone.rc
    ];
    nativeBuildInputs = [ pkgs.git ];
    args = ''
      ${nativeBootstrap} ${cloneRepository} "$out"
    '';
  };
  native-release-tests = vmTest "native-release-tests" {
    script = ./native_releases.py;
    files = [ ./releases.nix ];
    args = ''
      ${nativeBootstrap} "$out"
    '';
  };
  benchmark-native = pkgs.writeShellApplication {
    name = "benchmark-native";
    text = ''
      exec ${python}/bin/python ${testSupport [ ./native_performance.py ]}/native_performance.py \
        ${pkgs.qemu}/bin/qemu-system-x86_64 ${vm}/9front.qcow2 \
        ${nativeBootstrap} "''${1:-nix9-performance}"
    '';
  };
  native-update-tests = vmTest "native-update-tests" {
    script = ./native_update.py;
    nativeBuildInputs = [ pkgs.nix ];
    args = ''
      ${nativeBootstrap} ${nativePackageSource} "$out"
    '';
  };
  native-reproducibility-tests = vmTest "native-reproducibility-tests" {
    script = ./native_reproducibility.py;
    files = [
      ./reproducibility.nix
      ./artifacts.py
    ];
    nativeBuildInputs = [ pkgs.nix ];
    args = ''
      ${nixPackage} ${nixPackage.guestPrefix} \
      ${nativePackagesArchive} ${nativePackagesArchive.guestPrefix} "$out"
    '';
  };
}
