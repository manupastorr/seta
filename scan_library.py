#!/usr/bin/env python3
"""Scan tracks + To Curate, analyze audio, build library.json for the Seta UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
from pathlib import Path

from camelot import mix_score
from config import curate_root, tracks_root

APP_DIR = Path(__file__).resolve().parent
TRACKS_ROOT = tracks_root()
CURATE_ROOT = curate_root()
CACHE_PATH = APP_DIR / "cache.json"
LIBRARY_PATH = APP_DIR / "library.json"
AUDIO_EXTS = {".wav", ".aiff", ".aif", ".flac", ".mp3"}
PARALLEL_CACHE_SAVE_EVERY = 25
# soundcloud-set-id writes short Shazam probe clips here — not library tracks.
SET_ID_SAMPLE_DIR = "samples"
SET_ID_SAMPLE_PREFIX = "sample_"


def is_scannable_audio(path: Path) -> bool:
    if path.suffix.lower() not in AUDIO_EXTS:
        return False
    if SET_ID_SAMPLE_DIR in path.parts and path.stem.startswith(SET_ID_SAMPLE_PREFIX):
        return False
    return True


def discover_files(limit: int | None = None) -> list[Path]:
    files: list[Path] = []
    for root in (TRACKS_ROOT, CURATE_ROOT):
        if not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            if "tools" in Path(dirpath).parts:
                continue
            for name in filenames:
                path = Path(dirpath) / name
                if is_scannable_audio(path):
                    files.append(path)
    files.sort()
    if limit:
        files = files[:limit]
    return files


def parse_filename(path: Path) -> tuple[str, str]:
    stem = path.stem
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


def classify_path(path: Path) -> dict:
    path = path.resolve()
    if path.is_relative_to(TRACKS_ROOT):
        rel = path.relative_to(TRACKS_ROOT)
        parts = rel.parts
        return {
            "source": "tracks",
            "genre": parts[0] if len(parts) > 1 else "Unknown",
            "batch": None,
        }
    if path.is_relative_to(CURATE_ROOT):
        rel = path.relative_to(CURATE_ROOT)
        parts = rel.parts
        return {
            "source": "to_curate",
            "genre": parts[0] if len(parts) > 1 else "Uncategorized",
            "batch": parts[0] if len(parts) > 1 else None,
        }
    return {"source": "other", "genre": "Other", "batch": None}


def track_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]


def file_sig(path: Path) -> dict:
    stat = path.stat()
    return {"mtime": int(stat.st_mtime), "size": stat.st_size}


def waveform_track_fields(analysis: dict) -> dict:
    wf = analysis.get("waveform")
    if not wf or not wf.get("peak"):
        return {}
    return {
        "waveform_version": wf.get("version"),
        "waveform_peak": wf.get("peak"),
        "waveform_low": wf.get("low"),
        "waveform_mid": wf.get("mid"),
        "waveform_high": wf.get("high"),
    }


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def cached_analysis(path: Path, cache: dict) -> dict | None:
    from analyze import ANALYSIS_VERSION

    key = str(path.resolve())
    sig = file_sig(path)
    cached = cache.get(key)
    if (
        cached
        and cached.get("mtime") == sig["mtime"]
        and cached.get("size") == sig["size"]
        and cached.get("analysis_version") == ANALYSIS_VERSION
    ):
        return cached
    return None


def analyze_if_needed(path: Path, cache: dict) -> dict:
    from analyze import analyze_track

    key = str(path.resolve())
    cached = cached_analysis(path, cache)
    if cached:
        return cached
    sig = file_sig(path)

    result = analyze_track(path)
    entry = {**sig, **result}
    cache[key] = entry
    return entry


def _analyze_worker(path_str: str) -> tuple[str, dict, dict]:
    from analyze import analyze_track

    path = Path(path_str)
    sig = file_sig(path)
    result = analyze_track(path)
    return path_str, sig, result


def build_edges(tracks: list[dict], min_score: float = 0.55, max_edges: int = 12000) -> list[dict]:
    edges: list[dict] = []
    for i, a in enumerate(tracks):
        if a.get("bpm") is None or not a.get("key"):
            continue
        for b in tracks[i + 1 :]:
            if b.get("bpm") is None or not b.get("key"):
                continue
            score = mix_score(a["key"], b["key"], a["bpm"], b["bpm"])
            if score >= min_score:
                edges.append(
                    {
                        "source": a["id"],
                        "target": b["id"],
                        "score": round(score, 3),
                    }
                )
    edges.sort(key=lambda e: e["score"], reverse=True)
    return edges[:max_edges]


def track_record(path: Path, analysis: dict) -> dict:
    path_str = str(path.resolve())
    meta = classify_path(path)
    artist, title = parse_filename(path)
    return {
        "id": track_id(path),
        "path": path_str,
        "artist": artist,
        "title": title,
        "source": meta["source"],
        "genre": meta["genre"],
        "batch": meta["batch"],
        "duration_sec": analysis.get("duration_sec"),
        "bpm": analysis.get("bpm"),
        "bpm_raw": analysis.get("bpm_raw"),
        "bpm_octave_corrected": analysis.get("bpm_octave_corrected", False),
        "bpm_source": analysis.get("bpm_source"),
        "bpm_confidence": analysis.get("bpm_confidence"),
        "key": analysis.get("key"),
        "energy": analysis.get("energy", 0.5),
        "vocals": analysis.get("vocals"),
        "vocals_confidence": analysis.get("vocals_confidence"),
        "analysis_error": analysis.get("analysis_error"),
        **waveform_track_fields(analysis),
    }


def scan_sequential(files: list[Path], cache: dict) -> list[dict]:
    tracks: list[dict] = []
    for idx, path in enumerate(files, 1):
        analysis = analyze_if_needed(path, cache)
        if idx % 25 == 0 or idx == len(files):
            print(f"  analyzed {idx}/{len(files)}")
        tracks.append(track_record(path, analysis))
    save_cache(cache)
    return tracks


def scan_parallel(files: list[Path], cache: dict, workers: int) -> list[dict]:
    pending: list[str] = []
    results: dict[str, dict] = {}

    for path in files:
        path_str = str(path.resolve())
        cached = cached_analysis(path, cache)
        if cached:
            results[path_str] = cached
        else:
            pending.append(path_str)

    done = len(results)
    if done:
        print(f"  cached {done}/{len(files)}")
    if pending:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_analyze_worker, p) for p in pending]
            for future in as_completed(futures):
                path_str, sig, result = future.result()
                entry = {**sig, **result}
                cache[path_str] = entry
                results[path_str] = entry
                done += 1
                if done % 25 == 0 or done == len(files):
                    print(f"  analyzed {done}/{len(files)}")
                if done % PARALLEL_CACHE_SAVE_EVERY == 0 or done == len(files):
                    save_cache(cache)
    save_cache(cache)
    return [track_record(path, results[str(path.resolve())]) for path in files]


def scan(limit: int | None = None, workers: int = 4, skip_edges: bool = False) -> dict:
    files = discover_files(limit=limit)
    print(f"Found {len(files)} audio files")

    cache = load_cache()
    if workers > 1 and len(files) > 1:
        try:
            tracks = scan_parallel(files, cache, workers)
        except BrokenProcessPool:
            print("Parallel scan worker crashed; retrying with one worker.")
            tracks = scan_sequential(files, cache)
    else:
        tracks = scan_sequential(files, cache)

    tracks.sort(key=lambda t: (t["source"], t["genre"], t["artist"].lower(), t["title"].lower()))

    library = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tracks_root": str(TRACKS_ROOT),
        "curate_root": str(CURATE_ROOT),
        "track_count": len(tracks),
        "tracks": tracks,
        "edges": [] if skip_edges else build_edges(tracks),
    }
    LIBRARY_PATH.write_text(json.dumps(library, indent=2))
    print(f"Wrote {LIBRARY_PATH} ({len(tracks)} tracks, {len(library['edges'])} edges)")
    return library


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan DJ library for Seta")
    parser.add_argument("--limit", type=int, default=None, help="Only scan first N files")
    parser.add_argument("--workers", type=int, default=max(2, os.cpu_count() or 4) - 1)
    parser.add_argument("--skip-edges", action="store_true")
    args = parser.parse_args()
    scan(limit=args.limit, workers=args.workers, skip_edges=args.skip_edges)


if __name__ == "__main__":
    main()
