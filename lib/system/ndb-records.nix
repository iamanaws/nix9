records:
let
  error = message: throw "mkSystem: services.ndb.records ${message}";
  lines = record: if builtins.isList record then record else [ record ];
  values = value: if builtins.isList value then value else [ value ];
  validValue =
    value:
    builtins.isInt value || (builtins.isString value && builtins.match "[^\"\r\n]*" value != null);
  validLine =
    line:
    builtins.isAttrs line
    && line != { }
    && builtins.all (
      name:
      builtins.match "[a-zA-Z][a-zA-Z0-9_-]*" name != null
      && builtins.stringLength name < 32
      && values line.${name} != [ ]
      && builtins.all validValue (values line.${name})
    ) (builtins.attrNames line);
  renderLine =
    line:
    builtins.concatStringsSep " " (
      builtins.concatLists (
        map (name: map (value: "${name}=\"${toString value}\"") (values line.${name})) (
          builtins.attrNames line
        )
      )
    );
in
if
  !builtins.isList records
  || !builtins.all (record: lines record != [ ] && builtins.all validLine (lines record)) records
then
  error "require nonempty attribute sets or lists of lines, with attribute names shorter than 32 bytes and string/integer values without double quotes or newlines"
else
  builtins.concatStringsSep "\n\n" (
    map (record: builtins.concatStringsSep "\n\t" (map renderLine (lines record))) records
  )
