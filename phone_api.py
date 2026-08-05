"""
Jarvis phone remote API helpers.

iPhone (or any browser) talks to the orchestrator over HTTP.
Optional shared secret: JARVIS_PHONE_TOKEN (Bearer token).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

from fastapi import Header, HTTPException, UploadFile

PHONE_TOKEN = os.environ.get("JARVIS_PHONE_TOKEN", "").strip()


def require_phone_auth(authorization: str | None = Header(default=None)) -> None:
    """If JARVIS_PHONE_TOKEN is set, require Authorization: Bearer <token>."""
    if not PHONE_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if token != PHONE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


def auth_required() -> bool:
    return bool(PHONE_TOKEN)


def lan_ips() -> list[str]:
    """Best-effort list of non-loopback IPv4 addresses on this Mac."""
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                ips.append(ip)
        finally:
            s.close()
    except OSError:
        pass

    try:
        out = subprocess.check_output(["ifconfig"], text=True, timeout=3)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet ") and "netmask" in line:
                ip = line.split()[1]
                if ip.startswith("127."):
                    continue
                if ip not in ips:
                    ips.append(ip)
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return ips


def is_hotspot_like() -> bool:
    """Detect iPhone-hotspot / tether style addressing (peer LAN often broken)."""
    ips = lan_ips()
    # Classic iPhone hotspot: 172.20.10.x
    if any(ip.startswith("172.20.10.") for ip in ips):
        return True
    # Seen on this Mac while tethered: 192.0.0.2 with /32 (not a real LAN)
    if any(ip.startswith("192.0.0.") for ip in ips):
        return True
    return False


def preferred_lan_hint(port: int = 8010) -> str:
    if is_hotspot_like():
        return (
            f"Hotspot/tether detected — phone usually cannot open the Mac by LAN IP. "
            f"Start with HTTPS: `./start_jarvis.sh --phone-https` then open the "
            f"printed https://…/phone URL (required for the 🎙 mic button)."
        )
    ips = lan_ips()
    private = [
        ip
        for ip in ips
        if ip.startswith("192.168.")
        or ip.startswith("10.")
        or (
            ip.startswith("172.")
            and not ip.startswith("172.20.10.")
        )
    ]
    # Filter link-local / vm bridges preferred last
    home = [ip for ip in private if not ip.startswith("192.168.64.")]
    pick = (home or private or [None])[0]
    if pick:
        return (
            f"Text on Wi‑Fi: http://{pick}:{port}/phone · "
            f"Mic button needs HTTPS: ./start_jarvis.sh --phone-https"
        )
    return (
        f"Start stack: ./start_jarvis.sh · Phone mic: ./start_jarvis.sh --phone-https"
    )


def audio_to_wav(src: Path) -> Path:
    """Convert phone recording (m4a/webm/mp4/…) to 16k mono wav via ffmpeg."""
    wav = src.with_suffix(".wav")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — install with brew install ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return wav


async def save_upload(upload: UploadFile, dest: Path) -> None:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio too large (max 12MB)")
    dest.write_bytes(data)
