"""Consume a signed cache from another 9front VM over read-only 9P."""

import re

from guest import boot


def check_network_cache(publisher, qemu, image, port, artifacts, sources):
    # Pin the key through the test console, independently of the 9P connection.
    output = publisher.command("cat /tmp/published.pub; echo")
    key = re.search(r"(?m)^nix9-native:[A-Za-z0-9+/]+=*$", output)
    if not key:
        raise RuntimeError("missing publisher's public key")
    publisher.command("aux/listen1 -t tcp!*!17010 /bin/exportfs -R -r /tmp/published >/tmp/cache-server.log >[2=1] &")
    with boot(qemu, image) as guest:
        guest.command(f"hget -o /tmp/nix-store {artifacts}/nix-store")
        guest.command("chmod +x /tmp/nix-store; path=(/tmp $path)")
        guest.command("NIX_REMOTE='local?store=/usr/local/nix/store&state=/usr/local/nix/state&log=/usr/local/nix/log'")
        guest.command("test ! -e /usr/local/nix/store && test ! -e /tmp/published")
        guest.command(f"package={sources['package']}; library={sources['library']}")
        guest.command(f"key='{key[0]}'; echo $key > /tmp/cache.pub")
        guest.command("mkdir -p /n/nix-cache")
        guest.command(f"srv -m tcp!10.0.2.2!{port} nix-cache /n/nix-cache")
        result = guest.command("cp /tmp/cache.pub /n/nix-cache/nix-cache-info; echo WRITE-STATUS:$status")
        if not re.search(r"(?m)^WRITE-STATUS:.+$", result):
            raise RuntimeError("remote 9P cache allowed writes")
        guest.command("cache='file:///n/nix-cache?store=/usr/local/nix/store'")
        guest.command("fn cached { nix-store --option substituters $cache --option trusted-public-keys $key $* }")
        result = guest.command("cached --realise $package --add-root /usr/local/nix/state/gcroots/remote")
        if "copying path" not in result or "building '" in result:
            raise RuntimeError(f"remote cache was not used: {result}")
        guest.command("nix-store --verify-path $package $library")
        publisher.crash()
        # Leave the disconnected mount in place: valid outputs need no server.
        guest.child.timeout = 60
        guest.command("cached --realise $package")
        guest.command("nix-store --gc")
        guest.command("$package/bin/lua -e 'print(6 * 7)'", "42")
        guest.command("unmount /n/nix-cache; rm /srv/nix-cache")
        guest.command("rm /usr/local/nix/state/gcroots/remote; nix-store --gc")
        guest.command("test ! -e $package && test ! -e $library")
    return "two VMs, read-only 9P, signed substitution, server loss and GC passed"
