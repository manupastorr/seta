"""Local paths and settings for track-graph (override via env or .env)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TRACKS_ROOT = Path.home() / "Music" / "tracks"
DEFAULT_CURATE_ROOT = Path.home() / "Downloads" / "To Curate"
DEFAULT_PORT = 8765


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if not raw:
        return default.expanduser().resolve()
    return Path(raw).expanduser().resolve()


def tracks_root() -> Path:
    return _path_from_env("TRACK_GRAPH_TRACKS_ROOT", DEFAULT_TRACKS_ROOT)


def curate_root() -> Path:
    return _path_from_env("TRACK_GRAPH_CURATE_ROOT", DEFAULT_CURATE_ROOT)


def allowed_roots() -> tuple[Path, ...]:
    return tracks_root(), curate_root()


def port() -> int:
    return int(os.environ.get("TRACK_GRAPH_PORT", DEFAULT_PORT))
