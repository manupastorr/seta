"""Lightweight BPM / key / energy analysis for DJ library tracks."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from camelot import pitch_class_to_camelot

ANALYSIS_SECONDS = 90
TARGET_SR = 22050

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


def _detect_bpm(y: np.ndarray, sr: int) -> float | None:
    if len(y) < sr * 8:
        return None
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    if tempo is None:
        return None
    bpm = float(np.atleast_1d(tempo)[0])
    while bpm < 80:
        bpm *= 2
    while bpm > 190:
        bpm /= 2
    return round(bpm, 1)


def _detect_energy(y: np.ndarray, sr: int) -> float:
    if len(y) < sr:
        return 0.5
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    rms_n = float(np.clip(np.mean(rms) * 8, 0, 1))
    cent_n = float(np.clip(np.mean(centroid) / 5000, 0, 1))
    return round(0.55 * rms_n + 0.45 * cent_n, 3)


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
            "duration_sec": duration_sec,
            "bpm": None,
            "key": None,
            "energy": 0.5,
            "analysis_error": str(exc),
        }

    return {
        "duration_sec": duration_sec,
        "bpm": _detect_bpm(y, sr),
        "key": _detect_key(y, sr)[0],
        "energy": _detect_energy(y, sr),
        "analysis_error": None,
    }
