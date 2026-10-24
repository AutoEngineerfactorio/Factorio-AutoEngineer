"""R07-A tests: hostile container payloads are refused before interpretation.

Offline only. The fixtures are synthetic and produced by this test module.
"""
import base64
import json
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import blueprint_codec  # noqa: E402
from blueprint_codec import BlueprintError, decode_payload  # noqa: E402
from blueprint_document import classify  # noqa: E402


def encode(payload: bytes) -> str:
    return "0" + base64.b64encode(zlib.compress(payload)).decode("ascii")


class ContainerRejectionTests(unittest.TestCase):
    def test_refuses_invalid_base64(self):
        for body in ("!!!!", "AAAA=", "A"):
            with self.subTest(body=body), self.assertRaises(BlueprintError):
                decode_payload("0" + body)

    def test_refuses_non_zlib_payload(self):
        body = base64.b64encode(b"not compressed at all").decode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + body)

    def test_refuses_truncated_zlib_payload(self):
        raw = zlib.compress(json.dumps({"a": 1}).encode("utf-8"))
        body = base64.b64encode(raw[: len(raw) // 2]).decode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + body)

    def test_refuses_payload_with_trailing_bytes(self):
        raw = zlib.compress(json.dumps({"a": 1}).encode("utf-8")) + b"junk"
        body = base64.b64encode(raw).decode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + body)

    def test_refuses_non_json_payloads(self):
        # Only text that is not JSON at all is refused here. Valid JSON that
        # is not a blueprint document is refused by the document layer.
        for payload in (b"not json", b"{unclosed", b"[1,"):
            with self.subTest(payload=payload[:12]), self.assertRaises(BlueprintError):
                decode_payload(encode(payload))

    def test_refuses_a_decompression_bomb(self):
        # A small compressed payload that expands far beyond the decoded limit.
        payload = zlib.compress(b"0" * (blueprint_codec.MAX_DECOMPRESSED_BYTES + 4096))
        body = base64.b64encode(payload).decode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + body)

    def test_refuses_an_oversized_compressed_payload(self):
        # More compressed bytes than the container limit allows.
        raw = b"\x00" * (blueprint_codec.MAX_COMPRESSED_BYTES + 1)
        body = base64.b64encode(raw).decode("ascii")
        with self.assertRaises(BlueprintError):
            decode_payload("0" + body)

    def test_refuses_a_non_object_document(self):
        for value in ("text", 12, [1, 2, 3], None):
            with self.subTest(value=value), self.assertRaises(BlueprintError):
                classify(value)


if __name__ == "__main__":
    unittest.main()
