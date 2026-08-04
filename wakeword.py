"""
Jarvis — Wake Word Loop

Listens continuously for "Hey Jarvis" using OpenWakeWord. On detection,
records the user's command, transcribes it, runs it through the shared
router (local / grok / cloud), and speaks the reply.

Run standalone:
    python wakeword.py

Requires the orchestrator's .env (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY,
and GROK_BUILD_ALLOWLIST for engineering work). The mac_agent must be
running separately if Mac control tools are needed.
"""

import os
import sys

import sounddevice as sd
from dotenv import load_dotenv
from openwakeword.model import Model as WakeModel

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from agent import routed_chat  # noqa: E402
from tts import speak  # noqa: E402
from voice import record_audio, transcribe  # noqa: E402

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280
WAKE_THRESHOLD = 0.5


def main():
    print("[JARVIS] Loading wake word model...")
    wake_model = WakeModel(wakeword_models=["hey_jarvis"])

    print("[JARVIS] Ready — say 'Hey Jarvis' to begin.")

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SAMPLES)
            audio_int16 = chunk.flatten()

            prediction = wake_model.predict(audio_int16)
            score = prediction.get("hey_jarvis", 0)

            if score >= WAKE_THRESHOLD:
                print("[JARVIS] Wake word detected!")
                wake_model.reset()

                audio = record_audio()
                text = transcribe(audio)

                if not text:
                    speak("I didn't catch that.")
                    print("[JARVIS] Ready — say 'Hey Jarvis' to begin.")
                    continue

                print(f"[JARVIS] You said: {text!r}")
                result = routed_chat(text)
                reply = result.get("reply") or ""
                print(
                    f"[JARVIS] routed_to={result.get('routed_to')} "
                    f"reason={result.get('reason')} model={result.get('model')}"
                )
                print(f"[JARVIS] Reply: {reply}")
                speak(reply)
                print("[JARVIS] Ready — say 'Hey Jarvis' to begin.")


if __name__ == "__main__":
    main()
