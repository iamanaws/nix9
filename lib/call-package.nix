scope: recipe: args:
let
  function = if builtins.isFunction recipe then recipe else import recipe;
in
function (builtins.intersectAttrs (builtins.functionArgs function) scope // args)
