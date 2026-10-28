"""Local NTP fixture shared by terminal and CPU-mode startup tests."""

import socketserver
import struct
import time

OFFSET = 120


def timestamp():
    seconds = time.time() + OFFSET + 2208988800
    whole = int(seconds)
    return struct.pack("!II", whole, int((seconds - whole) * 2**32))


class NTP(socketserver.BaseRequestHandler):
    def handle(self):
        packet, connection = self.request
        if len(packet) < 48 or packet[0] & 7 != 3:
            return
        reply = bytearray(48)
        reply[:4] = bytes((0x1c, 1, 6, 0xec))
        reply[12:16] = b"LOCL"
        reply[16:24] = timestamp()
        reply[24:32] = packet[40:48]
        reply[32:40] = timestamp()
        reply[40:48] = timestamp()
        connection.sendto(reply, self.client_address)
        self.server.replied.set()
