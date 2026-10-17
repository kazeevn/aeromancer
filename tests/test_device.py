import unittest

from co2monitor import device

KEY = bytes([0xC4, 0xC6, 0xC0, 0x92, 0x40, 0x23, 0xDC, 0x96])


def encrypt(key: bytes, plain: bytes) -> bytes:
    """Inverse of device.decrypt, to fabricate frames from older firmware."""
    ctmp = [((c >> 4) | (c << 4)) & 0xFF for c in device._CSTATE]
    phase3 = [(plain[i] + ctmp[i]) & 0xFF for i in range(8)]
    phase2 = [((phase3[i] << 3) | (phase3[(i + 1) % 8] >> 5)) & 0xFF for i in range(8)]
    phase1 = [phase2[i] ^ key[i] for i in range(8)]
    return bytes(phase1[o] for o in device._SHUFFLE)


def frame(op: int, value: int) -> bytes:
    hi, lo = value >> 8, value & 0xFF
    return bytes([op, hi, lo, (op + hi + lo) & 0xFF, 0x0D, 0, 0, 0])


class DecodeTest(unittest.TestCase):
    def test_plaintext_frame(self):
        self.assertEqual(device.decode_frame(KEY, frame(0x50, 812)), (0x50, 812))

    def test_encrypted_frame(self):
        self.assertEqual(device.decode_frame(KEY, encrypt(KEY, frame(0x42, 4718))), (0x42, 4718))

    def test_corrupt_frame(self):
        bad = bytearray(frame(0x50, 812))
        bad[3] ^= 0xFF
        self.assertIsNone(device.decode_frame(KEY, bytes(bad)))
        self.assertIsNone(device.decode_frame(KEY, b"\x00" * 4))

    def test_interpret(self):
        self.assertEqual(device.interpret(0x50, 812), ("co2", 812.0))
        self.assertEqual(device.interpret(0x42, 4718), ("temperature", 21.73))
        self.assertEqual(device.interpret(0x41, 4512), ("humidity", 45.12))
        self.assertIsNone(device.interpret(0x41, 0))
        self.assertIsNone(device.interpret(0x50, 25000))
        self.assertEqual(device.interpret(0x6E, 27168), ("op_6e", 27168.0))

    def test_ioctl_number(self):
        # HIDIOCSFEATURE(9) as computed by the kernel headers.
        self.assertEqual(device._hidiocsfeature(9), 0xC0094806)


if __name__ == "__main__":
    unittest.main()
