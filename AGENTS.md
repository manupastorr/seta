# Track Graph — agent notes

## Scope

This repo is the **graph browser tool** only (`tools/graph/`). It does not own track sorting, genre folders, or Rekordbox workflows.

For moving/sorting/classifying audio files, follow the parent library rules:

**`~/Music/tracks/AGENTS.md`**

## Paths

Defaults (override with `.env` or env vars):

| Variable | Default |
|----------|---------|
| `TRACK_GRAPH_TRACKS_ROOT` | `~/Music/tracks` |
| `TRACK_GRAPH_CURATE_ROOT` | `~/Downloads/To Curate` |
| `TRACK_GRAPH_PORT` | `8765` |

Copy `.env.example` → `.env` per machine. Do not commit `.env`.

| Path | Purpose |
|------|---------|
| `~/Music/tracks` | Approved library (`source: tracks`) |
| `~/Downloads/To Curate` | Intake (`source: to_curate`) |
| `.venv/` | Local Python venv (created by `start.sh`) |
| `library.json` / `cache.json` | Generated locally — do not commit |

## Run / develop

```bash
./start.sh                    # scan + serve on :8765
.venv/bin/python scan_library.py
.venv/bin/python server.py
```

After changing `analyze.py`, bump `ANALYSIS_VERSION` so the cache re-analyzes stale entries.

## Scanner rules

- Audio: `.wav`, `.aiff`, `.aif`, `.flac`, `.mp3`
- Skip `tools/` tree while walking
- **Skip** `…/samples/sample_*.wav` — soundcloud-set-id Shazam clips, not tracks
- Do not sort or move `To Curate` unless the user explicitly asks

## BPM analysis

Unified resolver in `analyze.py` (see `ANALYSIS_VERSION`):

1. **Tagged ≥100 BPM** — trust store tag (Soundeo/Beatport full-tempo tags).
2. **Tagged 68–92 BPM** — half-time tag zone; double only when librosa also anchors ~140–165 BPM (peak techno) or ambiguous raw + close margin. Organic/cumbia tags stay slow.
3. **No tag** — score librosa octave candidates; prefer primary tempo when a half-time octave was picked; lift obvious psy/techno false halves (~72 → ~140 when scores are close). Prefer half-time when librosa primary is ~155–180 but onset favours ~78–95 (downtempo/organic).

UI fields: `bpm`, `bpm_raw`, `bpm_octave_corrected`, `bpm_source`, `bpm_confidence`

Map BPM domain: **70–180**. Bump `ANALYSIS_VERSION` after logic changes.

## UI conventions

- Single frontend file: `static/index.html` (D3, no build step)
- **Mix map** — BPM/energy placement; **Explore** — same BPM/energy grid with link forces and draggable nodes
- Set-moment clouds are fixed BPM×energy zones (visual only); toggle **Set moments**
- Keep changes minimal; no new dependencies without good reason

## Git

- Commit app code only (`library.json`, `cache.json`, audio stay ignored)
- Remote: `manupastorr/track-graph` on GitHub
