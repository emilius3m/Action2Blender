import json
import select
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from action2blender.transport import PoseServer, validate_message


def send_line(file, value):
    file.write(json.dumps(value).encode("utf-8") + b"\n")
    file.flush()


def read_line(file):
    return json.loads(file.readline())


class TransportTests(unittest.TestCase):
    def test_take_requires_nonempty_id(self):
        with self.assertRaisesRegex(ValueError, "Invalid take ID"):
            validate_message({"type": "take", "id": "", "events": [{}]})

    def setUp(self):
        self.server = PoseServer("127.0.0.1", 0, "test-token")
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def connect(self):
        client = socket.create_connection(self.server.server_address, timeout=2)
        client.settimeout(2)
        return client, client.makefile("rwb")

    def test_rejects_wrong_pairing_code(self):
        client, file = self.connect()
        with client, file:
            send_line(file, {"type": "hello", "version": 1, "token": "wrong"})
            self.assertEqual(read_line(file)["type"], "error")
        self.assertTrue(self.server.events.empty())

    def test_rejects_app_with_older_camera_mapping(self):
        client, file = self.connect()
        with client, file:
            send_line(file, {"type": "hello", "version": 1, "token": "test-token"})
            reply = read_line(file)
            self.assertEqual(reply["type"], "error")
            self.assertIn("Update the Action2Blender app", reply["message"])
        self.assertTrue(self.server.events.empty())

    def test_receives_pose_and_confirms_saved_take(self):
        client, file = self.connect()
        with client, file:
            send_line(file, {"type": "hello", "version": 1, "token": "test-token", "camera_control": 3})
            greeting = read_line(file)
            self.assertEqual(greeting["type"], "hello_ok")
            self.assertEqual(greeting["viewport_port"], 0)
            self.assertTrue(greeting["recenter_ack"])
            self.assertEqual(greeting["camera_control"], 3)
            send_line(file, {"type": "pose", "p": [1, 2, 3], "q": [0, 0, 0, 1]})
            self.assertEqual(read_line(file)["type"], "ack")
            self.assertEqual(self.server.events.get(timeout=2)["type"], "pose")
            send_line(
                file,
                {"type": "take", "id": "take-1", "events": [{"t": 0, "p": [0, 0, 0], "q": [0, 0, 0, 1]}]},
            )
            event = self.server.events.get(timeout=2)
            self.assertEqual(event["type"], "take")
            event["_response"].put({"type": "take_saved", "id": "take-1"})
            self.assertEqual(read_line(file), {"type": "take_saved", "id": "take-1"})

    def test_recenter_waits_for_blender_and_reports_its_result(self):
        client, file = self.connect()
        with client, file:
            send_line(file, {"type": "hello", "version": 1, "token": "test-token", "camera_control": 3})
            self.assertEqual(read_line(file)["type"], "hello_ok")
            send_line(file, {"type": "recenter", "p": [0, 0, 0], "q": [0, 0, 0, 1]})
            event = self.server.events.get(timeout=2)
            self.assertEqual(event["type"], "recenter")
            self.assertEqual(select.select([client], [], [], 0.1)[0], [])
            event["_response"].put({"type": "recenter_ok", "camera": "Camera"})
            self.assertEqual(read_line(file), {"type": "recenter_ok", "camera": "Camera"})

            send_line(file, {"type": "recenter", "p": [0, 0, 0], "q": [0, 0, 0, 1]})
            event = self.server.events.get(timeout=2)
            event["_response"].put({
                "type": "error",
                "message_type": "recenter",
                "message": "Select a scene camera first",
            })
            self.assertEqual(read_line(file)["message_type"], "recenter")

            send_line(file, {"type": "create_camera", "mode": "view", "p": [0, 0, 0], "q": [0, 0, 0, 1]})
            event = self.server.events.get(timeout=2)
            self.assertEqual(event["type"], "create_camera")
            event["_response"].put({"type": "recenter_ok", "camera": "Action2Blender Camera"})
            self.assertEqual(read_line(file)["camera"], "Action2Blender Camera")


if __name__ == "__main__":
    unittest.main()
