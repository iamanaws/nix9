{
  pkgs,
  abiCross,
  apeCross,
  ar,
  cc,
  buildTools,
  compressedText,
  clone,
  development,
  guestDevelopment,
  guestEnvironment,
  hello,
  helloCross,
  libbz2,
  libbz2Consumer,
  lua,
  luaPackage,
  mk,
  python,
  rc,
  secCross,
  sha1sum,
  sha1sumPackage,
  stdenvCross,
  testSupport,
  vm,
  vmTest,
  yacc,
}:
{
  stdenv-tests = vmTest "stdenv-tests" {
    script = ./smoke.py;
    args = ''
      ${stdenvCross}/bin/answer 'cross stdenv PASS'
      mkdir -p "$out"
      echo '{"cross-stdenv": "passed"}' > "$out/results.json"
    '';
  };
  build-tools-tests = vmTest "build-tools-tests" {
    script = ./build_tools.py;
    files = [ ./build-tools.rc ];
    args = ''
      ${buildTools} ${rc}/bin/rc ${compressedText} "$out"
    '';
  };
  mk-tests = vmTest "mk-tests" {
    script = ./mk.py;
    files = [ ./mkfile ];
    args = ''
      ${mk}/bin/mk "$out"
    '';
  };
  ar-tests = vmTest "ar-tests" {
    script = ./ar.py;
    args = ''
      ${ar}/bin/ar ${abiCross} "$out"
    '';
  };
  cc-tests = vmTest "cc-tests" {
    script = ./c_abi.py;
    args = ''
      ${./c-abi} ${abiCross} "$out" ${cc}
    '';
  };
  rc-yacc-tests = vmTest "rc-yacc-tests" {
    script = ./rc_yacc.py;
    files = [
      ./cross-rc.rc
      ./yacc/parser.y
    ];
    args = ''
      ${rc}/bin/rc ${yacc} "$out"
    '';
  };
  sha1sum-tests = vmTest "sha1sum-tests" {
    script = ./sha1sum.py;
    args = ''
      ${sha1sum.source} ${sha1sum}/bin/sha1sum "$out"
    '';
  };
  clone-tests = vmTest "clone-tests" {
    script = ./clone.py;
    files = [ ./clone.rc ];
    args = ''
      ${clone}/bin/clone "$out"
    '';
  };
  libsec-tests = vmTest "libsec-tests" {
    script = ./libsec.py;
    args = ''
      ${secCross} ${./libsec/generated.sha256} "$out"
    '';
  };
  guest-development-tests = vmTest "guest-development-tests" {
    script = ./guest_development.py;
    files = [
      ./c_abi.py
      ./ape.py
    ];
    args = ''
      ${guestDevelopment} ${guestDevelopment.guestPrefix} ${development.guestPrefix} \
      ${../pkgs/hello-c-cross/main.c} ${./c-abi} ${./ape/main.c} \
      ${./guest-development/bsd.c} "$out"
    '';
  };
  package-tests = vmTest "package-tests" {
    script = ./install_packages.py;
    args = ''
      ${guestEnvironment} ${guestEnvironment.guestPrefix} \
      ${luaPackage.guestPrefix} ${sha1sumPackage.guestPrefix} \
      ${./lua/fixture.lua} "$out"
    '';
  };
  libbz2-tests = vmTest "libbz2-tests" {
    script = ./libbz2.py;
    args = ''
      ${libbz2.source} ${libbz2} ${libbz2Consumer} ${./libbz2/main.c} "$out"
    '';
  };
  lua-tests = vmTest "lua-tests" {
    script = ./lua.py;
    args = ''
      ${lua.source} ${lua}/bin/lua ${./lua} \
      ${guestDevelopment} ${guestDevelopment.guestPrefix} ${development.guestPrefix} "$out"
    '';
  };
  ape-tests = vmTest "ape-tests" {
    script = ./ape.py;
    args = ''
      ${./ape/main.c} ${apeCross}/bin/ape-tests "$out"
    '';
  };
  c-abi-tests = vmTest "c-abi-tests" {
    script = ./c_abi.py;
    args = ''
      ${./c-abi} ${abiCross} "$out"
    '';
  };
  smoke-test = pkgs.writeShellApplication {
    name = "smoke-test";
    text = ''
      exec ${python}/bin/python ${testSupport [ ./smoke.py ]}/smoke.py \
        ${pkgs.qemu}/bin/qemu-system-x86_64 \
        ${vm}/9front.qcow2 ${hello}/bin/hello \
        'Hello from Nix on plan9/amd64!' "$@"
    '';
  };
  smoke-test-c-cross = pkgs.writeShellApplication {
    name = "smoke-test-c-cross";
    text = ''
      exec ${python}/bin/python ${testSupport [ ./smoke.py ]}/smoke.py \
        ${pkgs.qemu}/bin/qemu-system-x86_64 \
        ${vm}/9front.qcow2 ${helloCross}/bin/hello-c \
        'Hello from Nix-built C on 9front/amd64!' "$@"
    '';
  };
}
