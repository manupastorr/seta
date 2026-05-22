#!/usr/bin/env python3
"""Local server for the track graph UI and audio streaming."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from flask import Flask, Response, abort, jsonify, send_from_directory

GRAPH_DIR = Path(__file__).resolve().parent
STATIC_DIR = GRAPH_DIR / "static"
LIBRARY_PATH = GRAPH_DIR / "library.json"
TRACKS_ROOT = Path.home() / "Music" / "tracks"
CURATE_ROOT = Path.home() / "Downloads" / "To Curate"
ALLOWED_ROOTS = (TRACKS_ROOT.resolve(), CURATE_ROOT.resolve())

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
TRACK_INDEX: dict[str, dict] = {}


def load_library() -> dict:
    if not LIBRARY_PATH.exists():
        return {"tracks": [], "edges": [], "track_count": 0}
    data = json.loads(LIBRARY_PATH.read_text())
    TRACK_INDEX.clear()
    for track in data.get("tracks", []):
        TRACK_INDEX[track["id"]] = track
    return data


def allowed_path(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved == root or resolved.is_relative_to(root) for root in ALLOWED_ROOTS)


@app.get("/")
def index() -> Response:
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/library")
def api_library() -> Response:
    return jsonify(load_library())


@app.get("/api/audio/<track_id>")
def api_audio(track_id: str) -> Response:
    track = TRACK_INDEX.get(track_id) or next(
        (t for t in load_library().get("tracks", []) if t["id"] == track_id), None
    )
    if not track:
        abort(404)
    path = Path(track["path"])
    if not allowed_path(path) or not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    return send_from_directory(path.parent, path.name, mimetype=mime or "audio/wav")


def main() -> None:
    load_library()
    print("Track graph: http://127.0.0.1:8765")
    print(f"Library: {LIBRARY_PATH}")
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)


if __name__ == "__main__":
    main()
