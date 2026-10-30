{
  pkgs ? import <nix9>,
}:
let
  root = "/usr/glenda/nix9-bind";
  commandPackage = pkgs.mkDerivation {
    name = "binding-command";
    buildCommand = ''
      mkdir -p $out/bin
      echo '#!/bin/rc' > $out/bin/binding-command
      echo 'echo package-binding' >> $out/bin/binding-command
      chmod 755 $out/bin/binding-command
    '';
  };
  bind = source: {
    source = "${root}-${source}";
    target = "${root}-view";
  };
  make =
    extra:
    pkgs.mkSystem {
      imports = [
        {
          hostName = "binding-test";
          directories = builtins.listToAttrs (
            map
              (name: {
                name = "${root}-${name}";
                value.mode = "0750";
              })
              [
                "one"
                "two"
                "view"
                "other"
                "package"
              ]
          );
        }
        extra
      ];
    };
  invalid =
    binds:
    pkgs.mkSystem {
      hostName = "invalid";
      namespace = { inherit binds; };
    };
in
{
  one = make {
    namespace.binds = [
      ((bind "one") // { create = true; })
      ((bind "two") // { mode = "append"; })
      {
        source = "${commandPackage}/bin";
        target = "${root}-package";
      }
    ];
  };
  two = make {
    directories."${root}-view".mode = pkgs.lib.mkForce "0710";
    namespace.binds = [
      ((bind "one") // { mode = "append"; })
      (
        (bind "two")
        // {
          mode = "prepend";
          create = true;
        }
      )
    ];
  };
  removed = make { };
  unavailable = make { namespace.binds = [ (bind "missing") ]; };
  optional = make { namespace.binds = [ ((bind "missing") // { required = false; }) ]; };
  chain = make {
    namespace.binds = [
      (bind "one")
      {
        source = "${root}-view";
        target = "${root}-other";
      }
    ];
  };
  merged = make {
    imports = [
      ({ lib, ... }: { namespace.binds = lib.mkAfter [ (bind "two") ]; })
      ({ lib, ... }: { namespace.binds = lib.mkBefore [ (bind "one") ]; })
    ];
  };
  invalidSource = invalid [ ((bind "one") // { source = "relative"; }) ];
  invalidTarget = invalid [ ((bind "one") // { target = "relative"; }) ];
  traversal = invalid [ ((bind "one") // { source = "/usr/glenda/../other"; }) ];
  repeatedSlash = invalid [ ((bind "one") // { target = "/usr//glenda/view"; }) ];
  trailingSlash = invalid [ ((bind "one") // { source = "${root}-one/"; }) ];
  bareStoreSource = invalid [ ((bind "one") // { source = "/usr/local/nix/store/lost-reference"; }) ];
  storedTarget = invalid [ ((bind "one") // { target = "${commandPackage}/bin"; }) ];
  protected = invalid [ ((bind "one") // { target = "/bin"; }) ];
  protectedParent = invalid [ ((bind "one") // { target = "/usr/local"; }) ];
  internalSource = invalid [ ((bind "one") // { source = "/mnt/nix9-bind-manual"; }) ];
  self = invalid [ ((bind "one") // { target = "${root}-one"; }) ];
  recursive = invalid [ ((bind "one") // { target = "${root}-one/child"; }) ];
  nested = invalid [
    (bind "one")
    ((bind "two") // { target = "${root}-view/nested"; })
  ];
  invalidMode = invalid [ ((bind "one") // { mode = "before"; }) ];
  invalidCreate = invalid [ ((bind "one") // { create = "yes"; }) ];
  unknownOption = invalid [ ((bind "one") // { recursive = true; }) ];
  hiddenDirectory = make {
    directories."${root}-view/hidden" = { };
    namespace.binds = [ (bind "one") ];
  };
  mountedTarget = pkgs.mkSystem {
    hostName = "invalid";
    namespace.mounts.share.address = "tcp!files!17020";
    namespace.binds = [ ((bind "one") // { target = "/n/share/child"; }) ];
  };
}
