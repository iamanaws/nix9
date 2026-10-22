{
  pkgs,
  ar,
  cc,
  cloneRepository,
  compressedText,
  libmach,
  mk,
  nativeBootstrap,
  nativePackageSource,
  nativePackagesArchive,
  nixPackage,
  rc,
  vmTest,
}:
{
  native-bootstrap-tests = vmTest "native-bootstrap-tests" {
    script = ./native_bootstrap.py;
    files = [
      ./rc.nix
      ./bootstrap-inputs.nix
      ./cc.nix
      ./libc.c
      ./build-tools.nix
      ./build-tools.rc
    ];
    args = ''
      ${nativeBootstrap} \
      ${mk}/bin/mk ${rc}/bin/rc ${cc} ${ar}/bin/ar ${libmach}/lib/libmach.a ${compressedText} "$out"
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
