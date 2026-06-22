"""
Voice input for Jarvis — mic recording + faster-whisper transcription.

Records audio from the default mic, detects silence to know when the user
stopped talking, then transcribes with faster-whisper. The result is plain
text ready to feed into agent_loop().
"""

import io
import wave

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_THRESHOLD = 0.02
SILENCE_DURATION = 1.5
MAX_RECORD_SECONDS = 15

_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _model


def record_audio() -> np.ndarray:
    """Record from the mic until silence is detected or max duration is hit.

    Uses a continuous InputStream so the mic stays open (no blinking).
    Waits for speech to start, then stops after SILENCE_DURATION of quiet.
    """
    chunk_samples = int(SAMPLE_RATE * 0.1)
    silence_chunks = int(SILENCE_DURATION / 0.1)
    max_chunks = int(MAX_RECORD_SECONDS / 0.1)

    frames = []
    silent_count = 0
    heard_speech = False

    print("[VOICE] Listening...")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32") as stream:
        for _ in range(max_chunks):
            chunk, _overflowed = stream.read(chunk_samples)
            frames.append(chunk.copy())

            rms = np.sqrt(np.mean(chunk**2))
            if rms >= SILENCE_THRESHOLD:
                heard_speech = True
                silent_count = 0
            else:
                silent_count += 1

            if heard_speech and silent_count >= silence_chunks:
                break

    print("[VOICE] Done recording.")
    return np.concatenate(frames, axis=0).flatten()


def transcribe(audio: np.ndarray) -> str:
    """Transcribe audio array to text using faster-whisper."""
    model = _get_model()
    segments, _ = model.transcribe(audio, beam_size=3, language="en")
    text = " ".join(seg.text.strip() for seg in segments).strip()
    print(f"[VOICE] Transcribed: {text!r}")
    return text


def audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    """Convert float32 audio array to WAV bytes (for debugging/playback)."""
    int16_audio = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(int16_audio.tobytes())
    return buf.getvalue()
