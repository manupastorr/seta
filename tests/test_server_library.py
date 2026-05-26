"""Tests for in-memory library reload when library.json changes."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class ServerLibraryReloadTests(unittest.TestCase):
    def test_load_library_reloads_when_mtime_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = Path(tmp) / "library.json"
            lib_path.write_text(json.dumps({"tracks": [], "edges": [], "track_count": 0}))

            if "server" in sys.modules:
                del sys.modules["server"]

            with patch("server.LIBRARY_PATH", lib_path):
                server = importlib.import_module("server")
                server.LIBRARY_CACHE = None
                server.LIBRARY_MTIME = None
                server.TRACK_INDEX.clear()

                first = server.load_library(force=True)
                self.assertEqual(first["track_count"], 0)

                time.sleep(0.01)
                lib_path.write_text(
                    json.dumps(
                        {
                            "tracks": [{"id": "abc", "path": "/tmp/x.wav", "title": "T"}],
                            "edges": [],
                            "track_count": 1,
                        }
                    )
                )
                second = server.load_library()
                self.assertEqual(second["track_count"], 1)
                self.assertIn("abc", server.TRACK_INDEX)


class ServerLibraryScanTests(unittest.TestCase):
    def test_api_library_scan_runs_scanner_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = Path(tmp) / "library.json"
            lib_path.write_text(json.dumps({"tracks": [], "edges": [], "track_count": 0}))

            if "server" in sys.modules:
                del sys.modules["server"]

            with patch("server.LIBRARY_PATH", lib_path):
                with patch("server._run_scan", return_value=(0, "Wrote library.json")) as run_scan:
                    server = importlib.import_module("server")
                    server.LIBRARY_CACHE = None
                    server.LIBRARY_MTIME = None
                    server.TRACK_INDEX.clear()
                    server.app.config["TESTING"] = True
                    client = server.app.test_client()

                    response = client.post("/api/library/scan?skip_edges=1")

                    self.assertEqual(response.status_code, 200)
                    payload = response.get_json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["track_count"], 0)
                    run_scan.assert_called_once_with(skip_edges=True)

    def test_api_library_scan_rejects_parallel_requests(self) -> None:
        if "server" in sys.modules:
            del sys.modules["server"]

        server = importlib.import_module("server")
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        acquired = server._SCAN_LOCK.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            response = client.post("/api/library/scan")
            self.assertEqual(response.status_code, 409)
            payload = response.get_json()
            self.assertFalse(payload["ok"])
            self.assertIn("progress", payload["error"])
        finally:
            server._SCAN_LOCK.release()


if __name__ == "__main__":
    unittest.main()
