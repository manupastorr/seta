# Track Graph

Local web app to browse a DJ library on a **BPM × energy** map, with **Camelot** mix links, playback, and set-moment overlays.

Scans:

- `~/Music/tracks` — approved library
- `~/Downloads/To Curate` — intake / uncured batches

## Quick start

```bash
./start.sh
```

Opens **http://127.0.0.1:8765** after scanning (cached analysis is reused when files unchanged).

Venv lives at `tools/.venv` (shared with this app).

## Manual commands

```bash
# Scan only
../.venv/bin/python scan_library.py

# Scan with options
../.venv/bin/python scan_library.py --workers 4 --skip-edges

# Server only (requires library.json)
../.venv/bin/python server.py
```

## What it does

| Piece | Role |
|-------|------|
| `scan_library.py` | Walks audio folders, analyzes tracks, writes `library.json` + mix edges |
| `analyze.py` | BPM, Camelot key, energy (librosa, ~90s sample) |
| `camelot.py` | Wheel colors + mix compatibility scoring |
| `server.py` | Flask: UI, `/api/library`, audio streaming |
| `static/index.html` | Single-page D3 graph + player |

### Layouts

- **Mix map** — tracks placed by BPM (x) and energy (y); soft clustering when many share the same values
- **Explore** — force graph by mix links; BPM/energy grid + set-moment clouds stay as background reference

### Generated files (gitignored)

- `library.json` — scan output for the UI
- `cache.json` — per-file analysis cache
- `scan.log`

Re-scan after adding tracks or changing analysis (`ANALYSIS_VERSION` in `analyze.py`).

## Scanner exclusions

Not indexed as library tracks:

- `samples/sample_*.wav` under `To Curate` — short clips from **soundcloud-set-id** set identification (Shazam probes). Keep `tracklist.md` / `tracklist.json`; delete `samples/` when done.

## Library organization

Genre folders, sorting rules, and curation workflow live in the parent repo:

**[`~/Music/tracks/AGENTS.md`](../../AGENTS.md)**

This tool reads those folders; it does not move or classify files.

## Requirements

- Python 3.10+
- See `requirements.txt` — install via `start.sh` or `pip install -r requirements.txt`
