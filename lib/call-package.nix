scope: recipe: args:
let
  function = if builtins.isFunction recipe then recipe else import recipe;
  apply =
    function: args:
    let
      result = function args;
    in
    if builtins.isAttrs result then
      result
      // {
        override =
          overrides:
          apply function (args // (if builtins.isFunction overrides then overrides args else overrides));
      }
      // (
        if result ? overrideAttrs then
          {
            overrideAttrs = overrides: apply (args: (function args).overrideAttrs overrides) args;
          }
        else
          { }
      )
    else
      result;
in
apply function (builtins.intersectAttrs (builtins.functionArgs function) scope // args)
