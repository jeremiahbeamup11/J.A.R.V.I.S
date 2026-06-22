"""
Jarvis — Wake Word Loop

Listens continuously for "Hey Jarvis" using OpenWakeWord. On detection,
records the user's command, transcribes it, runs it through the agent loop,
and speaks the reply. Then goes back to listening.

Run standalone:
    python wakeword.py

Requires the orchestrator's .env (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY).
The mac_agent must be running separately if Mac control tools are needed.
"""

import os
import sys

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from openwakeword.model import Model as WakeModel

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from tools import TOOL_SCHEMAS, run_tool  # noqa: E402
from tts import speak  # noqa: E402
from voice import record_audio, transcribe  # noqa: E402

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280
WAKE_THRESHOLD = 0.5

from anthropic import Anthropic  # noqa: E402

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "You are Jarvis, a concise, capable voice assistant running on a Mac. "
    "You have direct control over the Mac through your tools: you can open "
    "apps, set the system volume, control media playback (play, pause, "
    "next, previous), open URLs in the browser, and run macOS Shortcuts. "
    "Always use your tools when the user asks you to do "
    "something you have a tool for — never say you can't do something that "
    "a tool handles. Keep spoken replies short and natural — you will be "
    "read aloud. Do not narrate that you are calling tools."
)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def agent_loop(user_message: str) -> str:
    """Run the Claude tool-calling loop until a final text answer."""
    messages = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = run_tool(block.name, block.input)
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    return "Stopped: hit the maximum number of tool rounds."


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
                reply = agent_loop(text)
                print(f"[JARVIS] Reply: {reply}")
                speak(reply)
                print("[JARVIS] Ready — say 'Hey Jarvis' to begin.")


if __name__ == "__main__":
    main()
