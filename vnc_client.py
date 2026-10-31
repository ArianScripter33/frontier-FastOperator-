"""Minimal RFB (VNC) client over a websocket: see the screen, move the mouse, press keys.

Only Raw encoding is requested: every server must support it and it needs no decoder.
The password is used for the handshake and never kept or logged.
"""
from __future__ import annotations

import hashlib
import io
import struct
import time
from typing import Optional

from Crypto.Cipher import DES
from PIL import Image
from websockets.sync.client import connect as ws_connect

CLICK_HOLD_SECONDS = 0.15  # The desktop ignores clicks held for less than 100 ms.
REPAINT_SECONDS = 1.0  # The desktop can take up to 1 s to repaint after an action.
SETTLE_TIMEOUT_SECONDS = 4.0
KEY_DELAY_SECONDS = 0.02

KEYSYMS = {
    "enter": 0xFF0D, "return": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "esc": 0xFF1B,
    "backspace": 0xFF08, "delete": 0xFFFF, "home": 0xFF50, "end": 0xFF57,
    "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54,
    "pageup": 0xFF55, "pagedown": 0xFF56, "space": 0x20,
    "ctrl": 0xFFE3, "shift": 0xFFE1, "alt": 0xFFE9,
    **{f"f{number}": 0xFFBD + number for number in range(1, 13)},
}
BUTTON_MASK = {"left": 1, "middle": 2, "right": 4}


class VncError(RuntimeError):
    pass


class DeadlineReached(VncError):
    """The task's time ended mid-action: nothing more may reach the desktop."""


def _vnc_auth_response(challenge: bytes, password: str) -> bytes:
    """VNC auth: DES of the challenge, with the password's key bits mirrored."""
    key = password.encode("latin-1", "replace")[:8].ljust(8, b"\0")
    key = bytes(int(f"{byte:08b}"[::-1], 2) for byte in key)
    return DES.new(key, DES.MODE_ECB).encrypt(challenge)


def keysym_for(char: str) -> int:
    code = ord(char)
    if char == "\n":
        return KEYSYMS["enter"]
    if char == "\t":
        return KEYSYMS["tab"]
    return code if code <= 0xFF else 0x01000000 | code


def valid_combo(combo: str) -> bool:
    names = [name.strip().lower() for name in combo.split("+")]
    return 1 <= len(names) <= 4 and all(name in KEYSYMS or len(name) == 1 for name in names)


class VncClient:
    def __init__(self, url: str, password: str, timeout: float = 20.0) -> None:
        self._buffer = bytearray()
        self._timeout = timeout
        self.stop_at = None  # Monotonic time after which typing stops, set by the task's owner.
        self._socket = ws_connect(url, subprotocols=["binary"], max_size=None, compression=None,
                                  open_timeout=timeout, close_timeout=2)
        try:
            self._handshake(password)
        except Exception:
            self.close()
            raise

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            frame = self._socket.recv(timeout=self._timeout)
            self._buffer.extend(frame.encode("latin-1") if isinstance(frame, str) else frame)
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def _send(self, data: bytes) -> None:
        self._socket.send(data)

    def _handshake(self, password: str) -> None:
        version = self._read(12)
        if not version.startswith(b"RFB "):
            raise VncError("Not an RFB server")
        minor = int(version[8:11])
        minor = 8 if minor >= 8 else (7 if minor == 7 else 3)
        self._send(b"RFB 003.%03d\n" % minor)
        if minor == 3:
            chosen = struct.unpack(">I", self._read(4))[0]
            if chosen == 0:
                raise VncError(self._failure_reason())
        else:
            count = self._read(1)[0]
            if count == 0:
                raise VncError(self._failure_reason())
            offered = self._read(count)
            chosen = 2 if 2 in offered else (1 if 1 in offered else 0)
            if not chosen:
                raise VncError("No supported VNC security type")
            self._send(bytes([chosen]))
        if chosen == 2:
            self._send(_vnc_auth_response(self._read(16), password))
        elif chosen != 1:
            raise VncError("No supported VNC security type")
        if chosen == 2 or minor == 8:
            if struct.unpack(">I", self._read(4))[0] != 0:
                raise VncError("VNC authentication failed")
        self._send(b"\x01")  # Shared session: the human viewer is not kicked out.
        self.width, self.height = struct.unpack(">HH", self._read(4))
        self._read(16)  # Server pixel format; replaced below.
        self._read(struct.unpack(">I", self._read(4))[0])  # Desktop name.
        # 32 bits per pixel, little endian, true colour: bytes arrive as B, G, R, X.
        self._send(b"\x00\0\0\0" + struct.pack(">BBBBHHHBBB3x", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        self._send(struct.pack(">BxHi", 2, 1, 0))  # SetEncodings: Raw.
        self._framebuffer = bytearray(self.width * self.height * 4)

    def _failure_reason(self) -> str:
        length = struct.unpack(">I", self._read(4))[0]
        return self._read(length).decode("utf-8", "replace")[:200]

    def _capture_raw(self) -> None:
        self._send(struct.pack(">BBHHHH", 3, 0, 0, 0, self.width, self.height))
        while True:
            kind = self._read(1)[0]
            if kind == 0:
                self._read_update()
                return
            if kind == 1:  # SetColourMapEntries
                _, _, count = struct.unpack(">BHH", self._read(5))
                self._read(count * 6)
            elif kind == 2:  # Bell
                continue
            elif kind == 3:  # ServerCutText
                self._read(3)
                self._read(struct.unpack(">I", self._read(4))[0])
            else:
                raise VncError(f"Unexpected server message {kind}")

    def _read_update(self) -> None:
        self._read(1)
        rectangles = struct.unpack(">H", self._read(2))[0]
        for _ in range(rectangles):
            x, y, width, height, encoding = struct.unpack(">HHHHi", self._read(12))
            if encoding != 0:
                raise VncError(f"Unexpected encoding {encoding}")
            pixels = self._read(width * height * 4)
            for row in range(height):
                start = ((y + row) * self.width + x) * 4
                self._framebuffer[start:start + width * 4] = pixels[row * width * 4:(row + 1) * width * 4]

    def screenshot_png(self) -> bytes:
        self._capture_raw()
        image = Image.frombuffer("RGB", (self.width, self.height), bytes(self._framebuffer), "raw", "BGRX", 0, 1)
        output = io.BytesIO()
        image.save(output, format="PNG", compress_level=3)
        return output.getvalue()

    def settled_screenshot(self, deadline: Optional[float] = None) -> bytes:
        """Wait for the repaint, then capture until two frames match: a fast capture shows the old screen."""
        time.sleep(REPAINT_SECONDS)
        limit = time.monotonic() + SETTLE_TIMEOUT_SECONDS
        if deadline is not None:
            limit = min(limit, deadline)
        previous = None
        while True:
            self._capture_raw()
            digest = hashlib.blake2b(self._framebuffer, digest_size=16).digest()
            if digest == previous or time.monotonic() >= limit:
                return self.screenshot_png()
            previous = digest
            time.sleep(0.4)

    def _pointer(self, x: int, y: int, mask: int = 0) -> None:
        self._send(struct.pack(">BBHH", 5, mask, x, y))

    def move(self, x: int, y: int) -> None:
        self._pointer(x, y)

    def click(self, x: int, y: int, button: str = "left") -> None:
        mask = BUTTON_MASK[button]
        self._pointer(x, y)
        time.sleep(0.05)
        self._pointer(x, y, mask)
        time.sleep(CLICK_HOLD_SECONDS)
        self._pointer(x, y)

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y)
        time.sleep(0.08)
        self.click(x, y)

    def scroll(self, x: int, y: int, direction: str, amount: int = 3) -> None:
        mask = 8 if direction == "up" else 16  # Wheel buttons 4 and 5.
        self._pointer(x, y)
        for _ in range(amount):
            self._pointer(x, y, mask)
            time.sleep(0.03)
            self._pointer(x, y)
            time.sleep(0.03)

    def _key(self, keysym: int, down: bool) -> None:
        self._send(struct.pack(">BBxxI", 4, 1 if down else 0, keysym))

    def press(self, combo: str) -> None:
        """Press a key or a combination such as `enter` or `ctrl+a`."""
        names = [name.strip().lower() for name in combo.split("+")]
        if self.stop_at is not None and time.monotonic() >= self.stop_at:
            raise DeadlineReached("Task time ended before a key press")
        if not valid_combo(combo):
            raise VncError("Unknown key combination")
        keysyms = [KEYSYMS[name] if name in KEYSYMS else keysym_for(name) for name in names]
        for keysym in keysyms:
            self._key(keysym, True)
            time.sleep(KEY_DELAY_SECONDS)
        for keysym in reversed(keysyms):  # Always released: a stuck Ctrl would corrupt later typing.
            self._key(keysym, False)
            time.sleep(KEY_DELAY_SECONDS)

    def type_text(self, text: str) -> None:
        for char in text:
            if self.stop_at is not None and time.monotonic() >= self.stop_at:
                raise DeadlineReached("Task time ended while typing")
            keysym = keysym_for(char)
            self._key(keysym, True)
            time.sleep(KEY_DELAY_SECONDS)
            self._key(keysym, False)
            time.sleep(KEY_DELAY_SECONDS)

    def replace_text(self, x: int, y: int, text: str) -> None:
        """Typing over existing text concatenates on this desktop, so select it first."""
        self.click(x, y)
        time.sleep(0.2)
        self.press("ctrl+a")
        time.sleep(0.1)
        self.type_text(text)

    def close(self) -> None:
        try:
            self._socket.close()
        except Exception:  # noqa: BLE001 - closing must never hide the task's result
            pass
