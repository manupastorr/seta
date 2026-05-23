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


if __name__ == "__main__":
    unittest.main()
