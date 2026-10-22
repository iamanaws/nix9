{ fetchurl }:
let
  revision = "228167f32bf5b14fcb41e52eab527a1c8531638a";
  source = fetchurl {
    url = "https://raw.githubusercontent.com/9front/9front/${revision}/sys/src/cmd/sha1sum.c";
    hash = "sha256-LIcy0GXxvp5cUoZsfZAwGvk0C+G05HmJSP/FRgupAHM=";
  };
in
{
  inherit source revision;
}
