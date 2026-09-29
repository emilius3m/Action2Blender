import struct
import unittest
import urllib.error
import urllib.request
import zlib

from addon.action2blender.viewport import ViewportServer, encode_rgba_png


class ViewportTests(unittest.TestCase):
    def test_png_orientation(self):
        bottom = bytes([255, 0, 0, 255])
        top = bytes([0, 0, 255, 255])
        png = encode_rgba_png(1, 2, bottom + top)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (1, 2))
        idat_length = struct.unpack(">I", png[33:37])[0]
        pixels = zlib.decompress(png[41 : 41 + idat_length])
        self.assertEqual(pixels, b"\x00" + top + b"\x00" + bottom)

    def test_authenticated_latest_frame(self):
        server = ViewportServer("127.0.0.1", "secret")
        server.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/frame?since=0&width=640"
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(url, timeout=2)
            self.assertEqual(rejected.exception.code, 403)
            first = encode_rgba_png(1, 1, bytes([255, 0, 0, 255]))
            latest = encode_rgba_png(1, 1, bytes([0, 255, 0, 255]))
            server.frames.put(first)
            server.frames.put(latest)
            request = urllib.request.Request(url, headers={"X-Action2Blender-Token": "secret"})
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["X-Frame-Seq"], "2")
                self.assertEqual(response.read(), latest)
            self.assertEqual(server.frames.active_width(), 640)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
