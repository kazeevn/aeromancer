"""Driver for the ZyAura / Holtek "USB-zyTemp" CO2 monitor (USB 04d9:a052).

The meter is a vendor HID device with 8-byte reports and no report IDs. After
the host sends an 8-byte key as a feature report, the meter streams frames of

    [op, value_hi, value_lo, checksum, 0x0d, 0, 0, 0]

Older firmware obfuscates each frame with the key (see ``decrypt``); newer
firmware sends them in the clear. Both are handled: a frame whose checksum is
already valid is taken as plaintext.

Besides CO2 and temperature, the meter sends codes we store raw as ``op_XX``
(docs/archive/zytemp-channels.md has the evidence):

    0x43  temperature, ~10x finer than 0x42
    0x6E  filtered NDIR absorption signal that CO2 is calculated from
    0x71  CO2 before the temperature, offset and altitude corrections
    0x4F  raw CO2-sensitive sample
    0x52, 0x56, 0x57  raw CO2-independent samples (reference beam?)
    0x6D  slow internal temperature

At power-up it also dumps 52 settings and constants, among them 0x4D, the
altitude setting in metres, which scales CO2 by roughly the pressure ratio.

We talk to the kernel's hidraw node directly, so no third-party packages are
needed. Reading it as a normal user requires the udev rule shipped in
``udev/70-aeromancer.rules``.
"""

from __future__ import annotations

import fcntl
import glob
import os
import select
import time
from dataclasses import dataclass
from typing import Iterator

VENDOR_ID = 0x04D9
PRODUCT_ID = 0xA052

OP_CO2 = 0x50  # ppm
OP_TEMPERATURE = 0x42  # 1/16 K
OP_HUMIDITY = 0x41  # 1/100 %RH, only on models with a humidity sensor

# The CO2 sensor reports garbage for the first few frames after power-up.
MAX_PLAUSIBLE_CO2 = 10_000

# Undocumented codes we have decoded (see the module docstring); still stored, but no longer a mystery.
EXPLAINED = frozenset({"op_43", "op_6e", "op_71", "op_4d"})

_CSTATE = (0x48, 0x74, 0x65, 0x6D, 0x70, 0x39, 0x39, 0x65)  # b"Htemp99e"
_SHUFFLE = (2, 4, 0, 7, 1, 6, 5, 3)


def _hidiocsfeature(length: int) -> int:
    # _IOC(_IOC_WRITE | _IOC_READ, 'H', 0x06, length)
    return (3 << 30) | (length << 16) | (ord("H") << 8) | 0x06


class DeviceNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class Reading:
    ts: float  # unix time, seconds
    quantity: str  # "co2" | "temperature" | "humidity" | "op_XX" for undocumented codes
    value: float


def decrypt(key: bytes, data: bytes) -> bytes:
    phase1 = [0] * 8
    for i, o in enumerate(_SHUFFLE):
        phase1[o] = data[i]
    phase2 = [phase1[i] ^ key[i] for i in range(8)]
    phase3 = [((phase2[i] >> 3) | (phase2[i - 1] << 5)) & 0xFF for i in range(8)]
    ctmp = [((c >> 4) | (c << 4)) & 0xFF for c in _CSTATE]
    return bytes((0x100 + phase3[i] - ctmp[i]) & 0xFF for i in range(8))


def _checksum_ok(frame: bytes) -> bool:
    return frame[4] == 0x0D and (frame[0] + frame[1] + frame[2]) & 0xFF == frame[3]


def decode_frame(key: bytes, data: bytes) -> tuple[int, int] | None:
    """Return ``(op, value)`` for a valid frame, ``None`` for a corrupt one."""
    if len(data) != 8:
        return None
    frame = bytes(data)
    if not _checksum_ok(frame):
        frame = decrypt(key, frame)
        if not _checksum_ok(frame):
            return None
    return frame[0], (frame[1] << 8) | frame[2]


def interpret(op: int, value: int) -> tuple[str, float] | None:
    """Map a frame to ``(quantity, value)``; undocumented codes become ``op_XX`` raw values."""
    if op == OP_CO2:
        if value > MAX_PLAUSIBLE_CO2:
            return None
        return "co2", float(value)
    if op == OP_TEMPERATURE:
        return "temperature", round(value / 16 - 273.15, 2)
    if op == OP_HUMIDITY:
        if value == 0:  # models without the sensor report zero
            return None
        return "humidity", value / 100
    return f"op_{op:02x}", float(value)


def find_hidraw() -> str:
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        for line in uevent.splitlines():
            if not line.startswith("HID_ID="):
                continue
            _bus, vid, pid = line.removeprefix("HID_ID=").split(":")
            if int(vid, 16) == VENDOR_ID and int(pid, 16) == PRODUCT_ID:
                return "/dev/" + os.path.basename(node)
    raise DeviceNotFound(f"no hidraw device with USB ID {VENDOR_ID:04x}:{PRODUCT_ID:04x}")


class CO2Monitor:
    """Context manager yielding ``Reading``s from the meter."""

    def __init__(self, path: str | None = None):
        self.path = path or find_hidraw()
        self.key = os.urandom(8)
        self._fd: int | None = None

    def __enter__(self) -> CO2Monitor:
        try:
            self._fd = os.open(self.path, os.O_RDWR)
        except PermissionError as e:
            raise PermissionError(
                f"cannot open {self.path}; install udev/70-aeromancer.rules "
                "(see README) or run as root"
            ) from e
        # Feature report: report ID 0 followed by the 8-byte key.
        fcntl.ioctl(self._fd, _hidiocsfeature(9), b"\x00" + self.key)
        return self

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def read(self, timeout: float) -> Reading | None:
        """Wait up to ``timeout`` seconds for one frame."""
        assert self._fd is not None, "use CO2Monitor as a context manager"
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return None
        data = os.read(self._fd, 8)  # raises OSError if the meter is unplugged
        decoded = decode_frame(self.key, data)
        if decoded is None:
            return None
        interpreted = interpret(*decoded)
        if interpreted is None:
            return None
        return Reading(time.time(), *interpreted)

    def readings(self, timeout: float = 1.0) -> Iterator[Reading | None]:
        """Yield readings forever; yields ``None`` on timeouts so callers can check for shutdown."""
        while True:
            yield self.read(timeout)
