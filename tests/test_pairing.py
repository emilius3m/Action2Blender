import struct
import unittest

from addon.action2blender.pairing import pairing_uri, qr_png


class PairingTests(unittest.TestCase):
    def test_pairing_uri(self):
        self.assertEqual(
            pairing_uri("192.168.1.3", 45767, "12345678"),
            "a2b://192.168.1.3:45767?v=1&t=12345678",
        )
        for host, port, token in [
            ("example.com", 45767, "12345678"),
            ("127.0.0.1", 45767, "12345678"),
            ("192.168.1.3", 0, "12345678"),
            ("192.168.1.3", 45767, "bad"),
        ]:
            with self.subTest(host=host, port=port, token=token):
                with self.assertRaises(ValueError):
                    pairing_uri(host, port, token)

    def test_qr_png(self):
        data = qr_png(pairing_uri("192.168.1.3", 45767, "12345678"))
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 200)


if __name__ == "__main__":
    unittest.main()
