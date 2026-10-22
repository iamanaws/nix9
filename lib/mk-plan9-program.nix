{ mkDerivation }:
{
  name,
  sources,
  includeDirs ? [ ],
  libraries ? [ ],
  cFlags ? [ ],
  meta ? { },
}:
let
  quote = value: "'" + builtins.replaceStrings [ "'" ] [ "''" ] "${value}" + "'";
  units = builtins.genList (index: {
    source = builtins.elemAt sources index;
    object = "unit-${toString index}.6";
  }) (builtins.length sources);
  flags = builtins.concatStringsSep " " (
    map quote cFlags ++ map (directory: "-I " + quote directory) includeDirs
  );
in
assert builtins.match "[a-zA-Z0-9][a-zA-Z0-9._+-]*" name != null;
assert sources != [ ];
mkDerivation {
  inherit name meta;
  buildInputs = libraries;
  buildCommand = ''
    ${builtins.concatStringsSep "\n" (
      map (unit: ''
        6c ${flags} -o ${unit.object} ${quote unit.source}
      '') units
    )}
    mkdir -p $out/bin
    6l -o $out/bin/${name} ${builtins.concatStringsSep " " (map (unit: unit.object) units)}
  '';
}
