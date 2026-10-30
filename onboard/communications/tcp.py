"""Length-prefixed frame transport over a stream socket (wired bench link).

Wire format: 4-byte big-endian length, then the protocol frame. Non-blocking
receive; partial reads are buffered.
"""

from __future__ import annotations

import socket
import struct

MAX_FRAME = 16 * 1024


class TcpFrameLink:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._sock.setblocking(False)
        self._buf = bytearray()
        self.connected = True

    def send(self, frame: bytes) -> None:
        if len(frame) > MAX_FRAME:
            raise ValueError("frame too large")
        self._sock.setblocking(True)
        try:
            self._sock.sendall(struct.pack(">I", len(frame)) + frame)
        except OSError:
            self.connected = False
        finally:
            self._sock.setblocking(False)

    def receive(self) -> list[bytes]:
        try:
            while True:
                data = self._sock.recv(65536)
                if not data:
                    self.connected = False
                    break
                self._buf.extend(data)
        except BlockingIOError:
            pass
        except OSError:
            self.connected = False
        frames = []
        while len(self._buf) >= 4:
            (n,) = struct.unpack_from(">I", self._buf)
            if n > MAX_FRAME:
                # Lost framing - drop the buffer and resynchronise on next data.
                self._buf.clear()
                break
            if len(self._buf) < 4 + n:
                break
            frames.append(bytes(self._buf[4 : 4 + n]))
            del self._buf[: 4 + n]
        return frames

    def close(self) -> None:
        self._sock.close()
