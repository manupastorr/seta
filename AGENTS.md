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
./start.sh                    # scan + serve; open printed URL (default :8765)
.venv/bin/python scan_library.py
.venv/bin/python server.py
```

`start.sh` creates `.venv` on first run, installs `requirements.txt`, sources `.env` if present, then scans and execs `server.py` (it does not auto-open a browser).

After changing `analyze.py`, bump `ANALYSIS_VERSION` so the cache re-analyzes stale entries.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_playback.mjs
```

Covers scanner path rules, Camelot/mix scoring, play-queue navigation (`static/playback.js`), and optional sanity check against a local `library.json` if present.

## Analysis vs Rekordbox

BPM, energy, and Camelot key are **local analysis aids** for map placement and mix hints—not Rekordbox truth. Energy and key have no separate confidence field; BPM exposes `bpm_confidence`. When `bpm_confidence` is low (UI/tooltip threshold **0.45**), verify tempo in Rekordbox before trusting grid position or mix links.

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

UI fields: `bpm`, `bpm_raw`, `bpm_octave_corrected`, `bpm_source`, `bpm_confidence`, `vocals`, `vocals_confidence`

`vocals` is heuristic (`yes` / `no` / `unclear`) from harmonic mid-band + `yin` pitch voicing on the first ~45s — not speech recognition. Show the player badge only when `vocals_confidence` ≥ 0.45.

Map BPM domain: **70–180**. Bump `ANALYSIS_VERSION` after logic changes.

## UI conventions

- Single frontend file: `static/index.html` (D3, no build step)
- Bottom **player dock** (full-width, SoundCloud-style): transport, title/artist, badges, wide waveform; sidebar is filters/map only
- Player uses a Serato-style RGB canvas waveform (red bass / green mids / blue highs); one `fetch` per track feeds both `<audio>` (blob URL) and waveform decode; peaks + blob URL cached in memory (24 tracks)
- **Mix map** — BPM/energy placement; **Explore** — same BPM/energy grid with link forces and draggable nodes
- Set-moment clouds are fixed BPM×energy zones (visual only): dance-floor arc plus **Close eyes**, **Chill groove**, and **Slow burn** (organic pulse at slow BPM); toggle **Set moments**
- Keep changes minimal; no new dependencies without good reason

## Git

- Commit app code only (`library.json`, `cache.json`, audio stay ignored)
- Remote: `manupastorr/track-graph` on GitHub
