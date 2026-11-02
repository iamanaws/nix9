"""Exercise native TFTP reads, option negotiation and rejected requests."""

import socket
import struct


class TftpError(RuntimeError):
    pass


def receive(connection):
    packet, peer = connection.recvfrom(65536)
    if len(packet) < 4:
        raise RuntimeError("short TFTP response")
    operation = struct.unpack("!H", packet[:2])[0]
    if operation == 5:
        raise TftpError(packet[4:].rstrip(b"\0").decode(errors="replace"))
    return operation, packet, peer


def read(address, filename, *, blocksize=512):
    request = b"\0\1" + filename.encode() + b"\0octet\0"
    if blocksize != 512:
        request += b"blksize\0" + str(blocksize).encode() + b"\0tsize\x000\0"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(10)
        connection.sendto(request, address)
        result = bytearray()
        expected = 1
        size = None
        while True:
            operation, packet, peer = receive(connection)
            if operation == 6:
                fields = packet[2:].rstrip(b"\0").split(b"\0")
                options = dict(zip(fields[::2], fields[1::2]))
                blocksize = int(options.get(b"blksize", b"512"))
                size = int(options[b"tsize"]) if b"tsize" in options else None
                connection.sendto(b"\0\4\0\0", peer)
                continue
            if operation != 3:
                raise RuntimeError("unexpected TFTP operation: " + str(operation))
            block = struct.unpack("!H", packet[2:4])[0]
            if block == (expected - 1) % 65536:
                connection.sendto(b"\0\4" + packet[2:4], peer)
                continue
            if block != expected % 65536:
                raise RuntimeError("out-of-order TFTP block")
            result.extend(packet[4:])
            connection.sendto(b"\0\4" + packet[2:4], peer)
            expected += 1
            if len(packet) - 4 < blocksize:
                if size is not None and size != len(result):
                    raise RuntimeError("TFTP size negotiation differs from returned data")
                return bytes(result)


def denied(address, filename, *, write=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(10)
        connection.sendto((b"\0\2" if write else b"\0\1") + filename.encode() + b"\0octet\0", address)
        try:
            receive(connection)
        except TftpError:
            return
    raise RuntimeError("TFTP accepted a forbidden request: " + filename)
