#!/usr/bin/env python3
"""Local server for the Seta UI and audio streaming."""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from config import allowed_roots, port, tracks_root

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
LIBRARY_PATH = APP_DIR / "library.json"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
TRACK_INDEX: dict[str, dict] = {}
LIBRARY_CACHE: dict | None = None
LIBRARY_MTIME: float | None = None
_SCAN_LOCK = threading.Lock()


def _library_mtime() -> float | None:
    if not LIBRARY_PATH.exists():
        return None
    return LIBRARY_PATH.stat().st_mtime


def load_library(*, force: bool = False) -> dict:
    global LIBRARY_CACHE, LIBRARY_MTIME
    mtime = _library_mtime()
    if LIBRARY_CACHE is not None and not force and mtime == LIBRARY_MTIME:
        return LIBRARY_CACHE
    if not LIBRARY_PATH.exists():
        LIBRARY_CACHE = {"tracks": [], "edges": [], "track_count": 0}
    else:
        LIBRARY_CACHE = json.loads(LIBRARY_PATH.read_text())
    LIBRARY_MTIME = mtime
    TRACK_INDEX.clear()
    for track in LIBRARY_CACHE.get("tracks", []):
        TRACK_INDEX[track["id"]] = track
    return LIBRARY_CACHE


def allowed_path(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots())


@app.get("/")
def index() -> Response:
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/library")
def api_library() -> Response:
    return jsonify(load_library())


@app.post("/api/library/reload")
def api_library_reload() -> Response:
    data = load_library(force=True)
    return jsonify({"ok": True, "track_count": data.get("track_count", 0)})


def _run_scan(*, skip_edges: bool) -> tuple[int, str]:
    python = APP_DIR / ".venv/bin/python"
    script = APP_DIR / "scan_library.py"
    if not python.is_file():
        return 127, f"Python scanner not found at {python}"
    args = [str(python), str(script)]
    if skip_edges:
        args.append("--skip-edges")
    try:
        result = subprocess.run(
            args,
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return 1, str(exc)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return result.returncode, output


@app.post("/api/library/scan")
def api_library_scan() -> Response:
    skip_edges = request.args.get("skip_edges", "1").lower() not in {"0", "false", "no"}
    if not _SCAN_LOCK.acquire(blocking=False):
        return jsonify({"ok": False, "error": "Scan already in progress"}), 409
    try:
        code, output = _run_scan(skip_edges=skip_edges)
        if code != 0:
            return jsonify({"ok": False, "error": output or f"scan exited {code}"}), 500
        data = load_library(force=True)
        return jsonify(
            {
                "ok": True,
                "track_count": data.get("track_count", 0),
                "output": output,
            }
        )
    finally:
        _SCAN_LOCK.release()


@app.get("/api/audio/<track_id>")
def api_audio(track_id: str) -> Response:
    load_library()
    track = TRACK_INDEX.get(track_id)
    if not track:
        abort(404)
    path = Path(track["path"])
    if not allowed_path(path) or not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    return send_from_directory(path.parent, path.name, mimetype=mime or "audio/wav")


def main() -> None:
    load_library()
    listen_port = port()
    print(f"Seta: http://127.0.0.1:{listen_port}")
    print(f"Library: {LIBRARY_PATH}")
    print(f"Tracks root: {tracks_root()}")
    app.run(host="127.0.0.1", port=listen_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
