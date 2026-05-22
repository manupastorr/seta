# Seta 🍄 — agent notes

## Scope

This repo is the **Seta map browser** only (`tools/seta/`). It does not own track sorting, genre folders, or Rekordbox workflows.

For moving/sorting/classifying audio files, follow the parent library rules:

**`~/Music/tracks/AGENTS.md`**

## Paths

Defaults (override with `.env` or env vars):

| Variable | Default |
|----------|---------|
| `SETA_TRACKS_ROOT` | `~/Music/tracks` |
| `SETA_CURATE_ROOT` | `~/Downloads/To Curate` |
| `SETA_PORT` | `8765` |

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

`vocals` is heuristic (`yes` / `no` / `unclear`) from harmonic mid-band + `yin` pitch voicing on the first ~45s — not speech recognition. Stricter thresholds in v9; show the player badge only when `vocals_confidence` ≥ 0.45.

Waveform fields on each track: `waveform_version`, `waveform_peak`, `waveform_low`, `waveform_mid`, `waveform_high` (400 bars from the first ~90s analysis window — intro/main preview, not full-track shape).

Map BPM domain: **70–180**. Intensity **values** stay **0–1** in `library.json`; the map **Y axis** runs from a library-wide adaptive floor (p3 of scanned energies, padded, min span 0.4) up to **1.0** so dense libraries spread vertically without clipping peak tracks. Set-zone filters still use raw 0–1 energy. Bump `ANALYSIS_VERSION` after analysis logic changes.

## UI conventions

- Single frontend file: `static/index.html` (D3, no build step)
- Bottom **player dock** (full-width, SoundCloud-style): transport, title/artist, badges, wide waveform; left **mix dock** holds the Neighbors toggle and mix queue (filters stay in the top bar)
- **Keyboard shortcuts** (`?` opens help): Space play/pause, ←/→ prev/next track, Shift+←/→ seek, `/` search, `n` neighbors, `r` reset view, ↑/↓ mix queue when neighbors on, Esc peels filters/search/neighbors/view
- Player uses a Serato-style RGB canvas waveform (red bass / green mids / blue highs); peaks come from `library.json` when present (scan-time, 400 bars); otherwise one `fetch` + client decode. Playback uses the same fetch (blob URL), cached in memory (24 tracks)
- `./start.sh --quick` runs `scan_library.py --skip-edges` for faster rescans when only adding tracks
- **Mix map** — BPM/energy placement; **Explore** — same BPM/energy grid with link forces and draggable nodes
- Changing filters (set zones, Camelot, genre, BPM range, search, library source) auto-zooms to the visible filtered nodes; clearing all filters resets the map view. Active filters show in a header summary chip; filter state persists in `sessionStorage` for the tab session
- Set-zone clouds are fixed BPM×energy regions (visual only); legend order follows set flow: **Open / low** → **Floor** → **Late** → **Wind-down** (Closing last). Title: **Set zones**
- Keep changes minimal; no new dependencies without good reason

## Git

- Commit app code only (`library.json`, `cache.json`, audio stay ignored)
- Remote: `manupastorr/seta` on GitHub
