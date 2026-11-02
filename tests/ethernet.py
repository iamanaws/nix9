"""Private Ethernet link between disposable QEMU guests."""

import socket
import struct
import threading


class Ethernet:
    """Connect the QEMU socket NICs and record DHCP messages on their shared link."""

    def __init__(self, names):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.2)
        self.peers = {}
        self.reserved = {}
        for name in names:
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer.bind(("127.0.0.1", 0))
            self.peers[name] = peer.getsockname()
            self.reserved[name] = peer
        self.messages = []
        self.requests = []
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.relay, daemon=True)
        self.thread.start()

    def backend(self, name, mac):
        if name in self.reserved:
            self.reserved.pop(name).close()
        return (f"socket,udp=127.0.0.1:{self.socket.getsockname()[1]},"
                f"localaddr=127.0.0.1:{self.peers[name][1]},mac={mac}")

    def relay(self):
        while not self.stopped.is_set():
            try:
                frame, sender = self.socket.recvfrom(65536)
            except socket.timeout:
                continue
            if sender not in self.peers.values():
                continue
            for peer in self.peers.values():
                if peer != sender:
                    self.socket.sendto(frame, peer)
            if len(frame) < 42 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
                continue
            offset = 14 + (frame[14] & 15) * 4
            ports = struct.unpack("!HH", frame[offset:offset + 4])
            packet = frame[offset + 8:]
            if ports[1] == 69 and packet[:2] in (b"\0\1", b"\0\2"):
                with self.lock:
                    self.requests.append(packet[2:].split(b"\0", 1)[0].decode("ascii", errors="replace"))
            # BOOTP and the DHCP magic cookie.
            if set(ports) != {67, 68}:
                continue
            if len(packet) < 240 or packet[236:240] != b"\x63\x82\x53\x63":
                continue
            options = {}
            position = 240
            while position < len(packet):
                key = packet[position]
                position += 1
                if key == 255:
                    break
                if key == 0:
                    continue
                if position >= len(packet):
                    break
                length = packet[position]
                position += 1
                options[key] = packet[position:position + length]
                position += length
            if len(options.get(53, b"")) != 1:
                continue
            with self.lock:
                self.messages.append({
                    "type": options[53][0],
                    "mac": packet[28:34].hex(),
                    "ciaddr": socket.inet_ntoa(packet[12:16]),
                    "yiaddr": socket.inet_ntoa(packet[16:20]),
                    "server": socket.inet_ntoa(options[54]) if len(options.get(54, b"")) == 4 else None,
                })

    def captured(self):
        with self.lock:
            return list(self.messages)

    def requested(self):
        with self.lock:
            return list(self.requests)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
        self.socket.close()
        for peer in self.reserved.values():
            peer.close()
