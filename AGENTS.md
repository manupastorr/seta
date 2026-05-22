# Track Graph — agent notes

## Scope

This repo is the **graph browser tool** only (`tools/graph/`). It does not own track sorting, genre folders, or Rekordbox workflows.

For moving/sorting/classifying audio files, follow the parent library rules:

**`~/Music/tracks/AGENTS.md`**

## Paths

| Path | Purpose |
|------|---------|
| `~/Music/tracks` | Approved library (`source: tracks`) |
| `~/Downloads/To Curate` | Intake (`source: to_curate`) |
| `tools/.venv` | Shared Python venv |
| `library.json` / `cache.json` | Generated locally — do not commit |

## Run / develop

```bash
./start.sh                    # scan + serve on :8765
../.venv/bin/python scan_library.py
../.venv/bin/python server.py
```

After changing `analyze.py`, bump `ANALYSIS_VERSION` so the cache re-analyzes stale entries.

## Scanner rules

- Audio: `.wav`, `.aiff`, `.aif`, `.flac`, `.mp3`
- Skip `tools/` tree while walking
- **Skip** `…/samples/sample_*.wav` — soundcloud-set-id Shazam clips, not tracks
- Do not sort or move `To Curate` unless the user explicitly asks

## BPM analysis

- Librosa often doubles tempo on organic/downtempo/cumbia (~86 shown as ~172)
- `analyze.py` halves suspicious **147–176 BPM** hits when half-time **70–95 BPM** fits onset scoring better
- UI fields: `bpm`, `bpm_raw`, `bpm_octave_corrected`
- Map BPM domain: **70–180**

## UI conventions

- Single frontend file: `static/index.html` (D3, no build step)
- **Mix map** — BPM/energy placement; **Explore** — force layout over same grid background
- Set-moment clouds are fixed BPM×energy zones (visual only); toggle **Set moments**
- Keep changes minimal; no new dependencies without good reason

## Git

- Commit app code only (`library.json`, `cache.json`, audio stay ignored)
- Remote: `manupastorr/track-graph` on GitHub
