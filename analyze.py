"""Lightweight BPM / key / energy analysis for DJ library tracks."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from camelot import pitch_class_to_camelot

ANALYSIS_SECONDS = 90
TARGET_SR = 22050
ANALYSIS_VERSION = 8
BPM_MIN = 70.0
BPM_MAX = 180.0
BPM_MAP_MIN = 70.0
HOP_LENGTH = 512

# Embedded tags below this are often half-time grids on peak-time electronic tracks.
HALFTIME_TAG_MIN = 68.0
HALFTIME_TAG_MAX = 92.0
FULL_TEMPO_TAG_MIN = 100.0
TECHNO_RAW_CLUSTER_MIN = 130.0
TECHNO_RAW_CLUSTER_MAX = 165.0
AMBIGUOUS_RAW_MIN = 90.0
AMBIGUOUS_RAW_MAX = 110.0

MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.28, 4.12, 2.52, 5.19, 2.39, 3.67]
)


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    try:
        info = sf.info(path)
        frames = min(info.frames, int(ANALYSIS_SECONDS * info.samplerate))
        audio, sr = sf.read(path, frames=frames, always_2d=True)
        mono = np.mean(audio, axis=1)
        if sr != TARGET_SR:
            mono = librosa.resample(mono, orig_sr=sr, target_sr=TARGET_SR)
            sr = TARGET_SR
        return mono.astype(np.float32), sr
    except Exception:
        mono, sr = librosa.load(
            path, sr=TARGET_SR, mono=True, duration=ANALYSIS_SECONDS
        )
        return mono, sr


def _detect_key(y: np.ndarray, sr: int) -> tuple[str | None, str | None]:
    if len(y) < sr * 8:
        return None, None
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    if np.allclose(chroma_mean, 0):
        return None, None

    best_score = -np.inf
    best_pc = 0
    best_mode = "major"
    for shift in range(12):
        rotated = np.roll(chroma_mean, -shift)
        major_score = float(np.dot(rotated, MAJOR_PROFILE))
        minor_score = float(np.dot(rotated, MINOR_PROFILE))
        if major_score > best_score:
            best_score = major_score
            best_pc = shift
            best_mode = "major"
        if minor_score > best_score:
            best_score = minor_score
            best_pc = shift
            best_mode = "minor"

    camelot = pitch_class_to_camelot(best_pc, best_mode)
    return camelot, best_mode


def _read_tagged_bpm(path: Path) -> float | None:
    """Read embedded BPM from download/store tags (TBPM) when present."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=False)
        if audio is None:
            return None
        for key in ("TBPM", "BPM"):
            if key not in audio:
                continue
            val = audio[key]
            if hasattr(val, "text"):
                raw = val.text[0]
            else:
                raw = val[0] if isinstance(val, list) else val
            bpm = float(str(raw).strip())
            if BPM_MIN <= bpm <= BPM_MAX:
                return round(bpm, 2)
            normalized = _normalize_bpm(bpm)
            if normalized is not None:
                return float(normalized)
    except Exception:
        return None
    return None


def _normalize_bpm(bpm: float) -> float | None:
    if not np.isfinite(bpm) or bpm <= 0:
        return None
    value = float(bpm)
    while value < BPM_MIN:
        value *= 2
    while value > BPM_MAX:
        value /= 2
    if BPM_MIN <= value <= BPM_MAX:
        return round(value, 1)
    return None


def _tempo_candidates(raw_tempos: np.ndarray) -> list[float]:
    candidates: set[float] = set()
    for tempo in np.atleast_1d(raw_tempos):
        if not np.isfinite(tempo) or tempo <= 0:
            continue
        for factor in (0.5, 1.0, 2.0):
            normalized = _normalize_bpm(float(tempo) * factor)
            if normalized is not None:
                candidates.add(normalized)
    return sorted(candidates)


def _score_bpm(onset_env: np.ndarray, sr: int, bpm: float) -> float:
    if len(onset_env) < 3:
        return 0.0
    ac = librosa.autocorrelate(onset_env, max_size=len(onset_env))
    peak = float(np.max(ac))
    if peak <= 0:
        return 0.0
    ac = ac / peak

    lag = 60.0 * sr / (bpm * HOP_LENGTH)
    total = 0.0
    weight = 0.0
    for harmonic, harmonic_weight in ((1.0, 1.0), (2.0, 0.35), (0.5, 0.2)):
        idx = int(round(lag * harmonic))
        if 1 <= idx < len(ac):
            lo = max(0, idx - 2)
            hi = min(len(ac), idx + 3)
            total += harmonic_weight * float(np.max(ac[lo:hi]))
            weight += harmonic_weight
    return total / weight if weight else 0.0


def _double_tag_bpm(tag: float) -> float:
    return round(tag * 2, 1)


def _tempo_near(value: float, target: float) -> bool:
    return abs(value - target) <= max(8.0, target * 0.08)


def _build_bpm_pool(
    raw: float | None, candidates: list[float], tag: float | None
) -> list[float]:
    pool: set[float] = set(candidates or [])
    if raw is not None and np.isfinite(raw):
        for factor in (0.5, 1.0, 2.0):
            normalized = _normalize_bpm(float(raw) * factor)
            if normalized is not None:
                pool.add(normalized)
    if tag is not None:
        pool.add(round(tag, 1))
        normalized_tag = _normalize_bpm(tag)
        if normalized_tag is not None:
            pool.add(normalized_tag)
        if HALFTIME_TAG_MIN <= tag <= HALFTIME_TAG_MAX:
            pool.add(_double_tag_bpm(tag))
    return sorted(bpm for bpm in pool if BPM_MIN <= bpm <= BPM_MAX)


def _rank_bpm_candidates(
    onset_env: np.ndarray, sr: int, pool: list[float]
) -> list[tuple[float, float]]:
    return sorted(
        ((bpm, _score_bpm(onset_env, sr, bpm)) for bpm in pool),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )


def _has_techno_double_anchor(
    tag: float, raw: float | None, candidates: list[float]
) -> bool:
    if raw is not None and TECHNO_RAW_CLUSTER_MIN <= raw <= TECHNO_RAW_CLUSTER_MAX:
        return True
    if raw is not None and AMBIGUOUS_RAW_MIN <= raw <= AMBIGUOUS_RAW_MAX:
        doubled = _double_tag_bpm(tag)
        return any(
            TECHNO_RAW_CLUSTER_MIN <= candidate <= TECHNO_RAW_CLUSTER_MAX
            and _tempo_near(candidate, doubled)
            for candidate in candidates
        )
    return False


def _resolve_tagged_bpm(
    onset_env: np.ndarray,
    sr: int,
    tag: float,
    raw: float | None,
    candidates: list[float],
) -> tuple[float, float, bool, str]:
    """Resolve BPM when a store/download tag exists."""
    tag = round(tag, 2)

    # Full-tempo tags from Soundeo/Beatport are usually trustworthy in this library.
    if tag >= FULL_TEMPO_TAG_MIN:
        return round(tag, 1), round(tag, 1), False, "tag"

    if HALFTIME_TAG_MIN <= tag <= HALFTIME_TAG_MAX:
        doubled = _double_tag_bpm(tag)
        tag_score = _score_bpm(onset_env, sr, tag)
        double_score = _score_bpm(onset_env, sr, doubled)

        if _has_techno_double_anchor(tag, raw, candidates):
            if double_score >= tag_score * 0.92:
                return doubled, round(tag, 1), True, "tag"
            margin = (tag_score - double_score) / tag_score if tag_score else 0.0
            if margin <= 0.13:
                return doubled, round(tag, 1), True, "tag"
            if (
                raw is not None
                and AMBIGUOUS_RAW_MIN <= raw <= AMBIGUOUS_RAW_MAX
                and margin <= 0.16
            ):
                return doubled, round(tag, 1), True, "tag"

        if (
            raw is not None
            and 166.0 <= raw <= 180.0
            and _tempo_near(raw, doubled)
            and double_score >= tag_score
            and _has_techno_double_anchor(tag, raw, candidates)
        ):
            return doubled, round(tag, 1), True, "tag"

        if double_score > tag_score * 1.15 and _has_techno_double_anchor(
            tag, raw, candidates
        ):
            return doubled, round(tag, 1), True, "tag"

        return round(tag, 1), round(tag, 1), False, "tag"

    return round(tag, 1), round(tag, 1), False, "tag"


def _resolve_analysis_bpm(
    onset_env: np.ndarray,
    sr: int,
    raw: float | None,
    candidates: list[float],
) -> tuple[float | None, float | None, bool]:
    """Resolve BPM from audio when no embedded tag exists."""
    pool = _build_bpm_pool(raw, candidates, None)
    if not pool:
        if raw is None:
            return None, None, False
        normalized = _normalize_bpm(float(raw))
        return normalized, round(float(raw), 1), False

    ranked = _rank_bpm_candidates(onset_env, sr, pool)
    best, best_score = ranked[0]
    octave_fixed = False

    # Lift to faster octave only for clear club-tempo grids (psy/techno/house).
    if raw is not None and np.isfinite(raw):
        raw_norm = _normalize_bpm(float(raw))
        if raw_norm is not None and best < raw_norm * 0.78:
            raw_score = _score_bpm(onset_env, sr, raw_norm)
            if 118.0 <= raw_norm <= 155.0 and raw_score >= best_score * 0.93:
                octave_fixed = True
                best = raw_norm
                best_score = raw_score
            elif (
                118.0 <= raw_norm <= 132.0
                and best <= 95.0
                and raw_score >= best_score * 0.82
            ):
                octave_fixed = True
                best = raw_norm
                best_score = raw_score

    # Librosa often doubles downtempo/organic (~82 heard as ~164).
    if best > 150.0:
        half = round(best / 2, 1)
        if 70.0 <= half <= 95.0:
            half_score = _score_bpm(onset_env, sr, half)
            if half_score >= best_score * 0.95:
                best = half
                best_score = half_score
                octave_fixed = True

    # Untagged psy/techno can score oddly on half-time; prefer floor tempo when close.
    if best < 78.0:
        for candidate, score in ranked:
            if 136.0 <= candidate <= 148.0 and score >= best_score * 0.80:
                if candidate != best:
                    octave_fixed = True
                best = candidate
                best_score = score
                break

    if (
        raw is not None
        and np.isfinite(raw)
        and best <= 95.0
        and float(raw) >= 150.0
        and best < float(raw) * 0.6
    ):
        octave_fixed = True

    return round(best, 1), round(float(raw), 1) if raw is not None else None, octave_fixed


def _detect_bpm(
    y: np.ndarray, sr: int
) -> tuple[float | None, float | None, bool, np.ndarray, list[float]]:
    if len(y) < sr * 8:
        return None, None, False, np.array([]), []

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
    primary, _ = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, hop_length=HOP_LENGTH
    )
    raw_bpm = float(np.atleast_1d(primary)[0])

    try:
        multi = librosa.feature.rhythm.tempo(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=HOP_LENGTH,
            aggregate=None,
            max_tempo=220,
        )
    except Exception:
        multi = np.array([raw_bpm])

    candidates = _tempo_candidates(np.concatenate([np.atleast_1d(multi), [raw_bpm]]))
    bpm, _, octave_fixed = _resolve_analysis_bpm(
        onset_env, sr, raw_bpm, candidates
    )
    return bpm, round(raw_bpm, 1), octave_fixed, onset_env, candidates


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _detect_vocals(y: np.ndarray, sr: int) -> tuple[str, float | None]:
    """Heuristic vocal presence: yes, no, or unclear, plus confidence in that label."""
    if len(y) < sr * 8:
        return "unclear", None

    vocal_window = sr * 45
    if len(y) > vocal_window:
        y = y[:vocal_window]

    y_harm, y_perc = librosa.effects.hpss(y, margin=2.0)
    harm_rms = float(np.sqrt(np.mean(y_harm**2)))
    perc_rms = float(np.sqrt(np.mean(y_perc**2)))
    harm_ratio = harm_rms / (harm_rms + perc_rms + 1e-9)

    mel = librosa.feature.melspectrogram(y=y_harm, sr=sr, n_mels=48, fmax=6000)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_mean = np.mean(mel_db, axis=1)
    vocal_band = float(np.mean(mel_mean[5:28]))
    edge_band = float(np.mean(np.concatenate([mel_mean[:5], mel_mean[28:]])))
    vocal_contrast = vocal_band - edge_band

    try:
        f0 = librosa.yin(
            y_harm,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C5"),
            sr=sr,
        )
        voiced_strength = float(np.mean(np.isfinite(f0)))
    except Exception:
        voiced_strength = 0.0

    flatness = librosa.feature.spectral_flatness(y=y_harm)[0]
    tonal_harm = _clip01(1.0 - float(np.mean(flatness)) * 10.0)

    vocal_score = (
        0.28 * _clip01((harm_ratio - 0.52) / 0.22)
        + 0.28 * _clip01((vocal_contrast - 1.5) / 4.0)
        + 0.30 * _clip01((voiced_strength - 0.12) / 0.28)
        + 0.14 * tonal_harm
    )
    inst_score = (
        0.40 * _clip01((0.48 - harm_ratio) / 0.18)
        + 0.35 * _clip01((0.08 - voiced_strength) / 0.08)
        + 0.25 * _clip01((2.0 - vocal_contrast) / 2.0)
    )

    if vocal_score >= 0.52 and vocal_score >= inst_score + 0.12:
        conf = _clip01(0.45 + (vocal_score - 0.52) * 1.1)
        return "yes", round(conf, 3)
    if inst_score >= 0.50 and inst_score >= vocal_score + 0.12:
        conf = _clip01(0.45 + (inst_score - 0.50) * 1.1)
        return "no", round(conf, 3)
    spread = abs(vocal_score - inst_score)
    conf = round(_clip01(0.35 + spread * 0.5), 3)
    return "unclear", conf


def _detect_energy(y: np.ndarray, sr: int) -> float:
    if len(y) < sr:
        return 0.5
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    rms_n = float(np.clip(np.mean(rms) * 8, 0, 1))
    cent_n = float(np.clip(np.mean(centroid) / 5000, 0, 1))
    flux = librosa.onset.onset_strength(y=y, sr=sr)
    flux_n = float(np.clip(np.std(flux) * 4, 0, 1))
    return round(0.5 * rms_n + 0.35 * cent_n + 0.15 * flux_n, 3)


def _estimate_bpm_confidence(
    onset_env: np.ndarray, sr: int, bpm: float | None, pool: list[float]
) -> float | None:
    if bpm is None or not pool:
        return None
    ranked = _rank_bpm_candidates(onset_env, sr, pool)
    if not ranked:
        return None
    chosen_score = next((score for candidate, score in ranked if candidate == bpm), ranked[0][1])
    if chosen_score <= 0:
        return None
    others = [score for candidate, score in ranked if candidate != bpm]
    second_score = max(others) if others else 0.0
    margin = max(0.0, (chosen_score - second_score) / chosen_score)
    return round(min(1.0, 0.35 + margin * 0.65), 3)


def analyze_track(path: Path) -> dict:
    duration_sec = None
    try:
        duration_sec = round(sf.info(path).duration, 2)
    except Exception:
        pass

    try:
        y, sr = _load_mono(path)
    except Exception as exc:
        return {
            "analysis_version": ANALYSIS_VERSION,
            "duration_sec": duration_sec,
            "bpm": None,
            "bpm_raw": None,
            "bpm_octave_corrected": False,
            "bpm_source": None,
            "bpm_confidence": None,
            "key": None,
            "energy": 0.5,
            "vocals": "unclear",
            "vocals_confidence": None,
            "analysis_error": str(exc),
        }

    vocals, vocals_confidence = _detect_vocals(y, sr)
    bpm, bpm_raw, bpm_octave_corrected, onset_env, tempo_candidates = _detect_bpm(y, sr)
    bpm_source = "analysis"

    tagged = _read_tagged_bpm(path)
    if tagged is not None:
        bpm, bpm_raw, bpm_octave_corrected, bpm_source = _resolve_tagged_bpm(
            onset_env, sr, tagged, bpm_raw, tempo_candidates
        )

    pool = _build_bpm_pool(bpm_raw, tempo_candidates, tagged)
    bpm_confidence = _estimate_bpm_confidence(onset_env, sr, bpm, pool)

    return {
        "analysis_version": ANALYSIS_VERSION,
        "duration_sec": duration_sec,
        "bpm": bpm,
        "bpm_raw": bpm_raw,
        "bpm_octave_corrected": bpm_octave_corrected,
        "bpm_source": bpm_source,
        "bpm_confidence": bpm_confidence,
        "key": _detect_key(y, sr)[0],
        "energy": _detect_energy(y, sr),
        "vocals": vocals,
        "vocals_confidence": vocals_confidence,
        "analysis_error": None,
    }
