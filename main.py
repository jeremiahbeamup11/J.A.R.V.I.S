"""
Jarvis — Milestone 2
Text-only Claude tool-calling loop over FastAPI.

Flow:
  POST /chat {"message": "..."}
    -> send to Claude with TOOL_SCHEMAS
    -> if Claude calls tools, run them, feed results back
    -> repeat until Claude returns a plain text answer
    -> return that answer

This is the core "brain" loop. Voice (STT/TTS) and wake word get bolted
onto the ends later — they do not change this loop.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from tools import TOOL_SCHEMAS, run_tool

load_dotenv()

MODEL = "claude-opus-4-8"
MAX_TOOL_ROUNDS = 8  # safety cap so the loop can't spin forever

SYSTEM_PROMPT = (
    "You are Jarvis, a concise, capable voice assistant. "
    "Use the available tools when the user asks you to control things or "
    "check status. Keep spoken replies short and natural — you will be "
    "read aloud. Do not narrate that you are calling tools."
)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
app = FastAPI(title="Jarvis")


class ChatRequest(BaseModel):
    message: str


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

        # If Claude isn't asking for a tool, we're done — return its text.
        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        # Append Claude's turn (which contains the tool_use blocks).
        messages.append({"role": "assistant", "content": response.content})

        # Run every tool Claude asked for and collect the results.
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

        # Feed the tool results back as the next user turn.
        messages.append({"role": "user", "content": tool_results})

    return "Stopped: hit the maximum number of tool rounds."


@app.get("/")
def health():
    return {"status": "jarvis online"}


@app.post("/chat")
def chat(req: ChatRequest):
    reply = agent_loop(req.message)
    return {"reply": reply}