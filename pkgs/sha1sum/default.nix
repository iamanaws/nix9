{ fetchurl, mkPlan9Program }:
let
  revision = "228167f32bf5b14fcb41e52eab527a1c8531638a";
  source = fetchurl {
    url = "https://raw.githubusercontent.com/9front/9front/${revision}/sys/src/cmd/sha1sum.c";
    hash = "sha256-LIcy0GXxvp5cUoZsfZAwGvk0C+G05HmJSP/FRgupAHM=";
  };
in
(mkPlan9Program {
  name = "sha1sum";
  sources = [ source ];
  meta = {
    description = "9front SHA-1 and SHA-2 checksum utility";
    homepage = "https://9front.org";
  };
}).overrideAttrs
  (_: {
    passthru = { inherit source revision; };
  })
