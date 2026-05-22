"""Lightweight BPM / key / energy analysis for DJ library tracks."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from camelot import pitch_class_to_camelot

ANALYSIS_SECONDS = 90
TARGET_SR = 22050
ANALYSIS_VERSION = 3
BPM_MIN = 70.0
BPM_MAX = 180.0
BPM_MAP_MIN = 70.0
HOP_LENGTH = 512

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
    """Prefer embedded BPM from download/store tags (TBPM) when present."""
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


def _maybe_halve_suspicious_tempo(
    onset_env: np.ndarray, sr: int, bpm: float
) -> tuple[float, bool]:
    """Halve common librosa double-time detections (e.g. 76→152, 86→172)."""
    if not (147.0 <= bpm <= 176.0):
        return bpm, False
    half_raw = bpm / 2
    if not (70.0 <= half_raw <= 95.0):
        return bpm, False
    half = round(half_raw, 1)
    full_score = _score_bpm(onset_env, sr, bpm)
    half_score = _score_bpm(onset_env, sr, half)
    if half_score >= full_score * 0.88:
        return half, True
    return bpm, False


def _detect_bpm(y: np.ndarray, sr: int) -> tuple[float | None, float | None, bool]:
    if len(y) < sr * 8:
        return None, None, False

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
    if not candidates:
        normalized = _normalize_bpm(raw_bpm)
        if normalized is None:
            return None, round(raw_bpm, 1), False
        corrected, fixed = _maybe_halve_suspicious_tempo(onset_env, sr, normalized)
        return corrected, round(raw_bpm, 1), fixed

    ranked = sorted(
        ((bpm, _score_bpm(onset_env, sr, bpm)) for bpm in candidates),
        key=lambda item: item[1],
        reverse=True,
    )
    best_bpm = ranked[0][0]
    corrected, fixed = _maybe_halve_suspicious_tempo(onset_env, sr, best_bpm)

    if not fixed:
        raw_normalized = _normalize_bpm(raw_bpm)
        if raw_normalized is not None and raw_normalized != corrected:
            alt, alt_fixed = _maybe_halve_suspicious_tempo(onset_env, sr, raw_normalized)
            if alt_fixed:
                corrected, fixed = alt, True

    return corrected, round(raw_bpm, 1), fixed


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
            "key": None,
            "energy": 0.5,
            "analysis_error": str(exc),
        }

    bpm, bpm_raw, bpm_octave_corrected = _detect_bpm(y, sr)
    bpm_source = "analysis"

    tagged = _read_tagged_bpm(path)
    if tagged is not None:
        bpm = tagged
        bpm_raw = tagged
        bpm_octave_corrected = False
        bpm_source = "tag"

    return {
        "analysis_version": ANALYSIS_VERSION,
        "duration_sec": duration_sec,
        "bpm": bpm,
        "bpm_raw": bpm_raw,
        "bpm_octave_corrected": bpm_octave_corrected,
        "bpm_source": bpm_source,
        "key": _detect_key(y, sr)[0],
        "energy": _detect_energy(y, sr),
        "analysis_error": None,
    }
