{ mkDerivation }:
{
  url,
  hash,
  name ? builtins.baseNameOf url,
}:
mkDerivation {
  inherit name url;
  outputHash = hash;
  outputHashAlgo = "";
  outputHashMode = "flat";
  buildCommand = ''
    rfork n
    $tools/bin/webfs -m /mnt/web -T 60000
    <>/mnt/web/clone {
      connection = /mnt/web/^`{$tools/bin/sed 1q}
      $tools/bin/echo -n url $url >[1=0]
      $tools/bin/cat $connection/body >$out
    }
  '';
}
