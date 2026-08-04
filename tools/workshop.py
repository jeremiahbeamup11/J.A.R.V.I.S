"""
Jarvis Workshop — design/engineering work products on the Mac.

Capability pattern (the "Tony Stark table" loop):
  1. Brain reasons about the problem (Claude).
  2. Brain builds a tangible 3D model (STL / Blender scene).
  3. Brain writes a short design brief next to the model.
  4. Mac agent opens the file / app so the user can see and spin it.

Engines (Milestone 11b):
  - primitives — pure-Python binary STL (always available)
  - blender    — named/colorized .blend + STL + GLB (when Blender installed)
  - auto       — blender if available, else primitives

No raw shell. Artifacts only land under WORKSHOP_DIR (allowlisted).
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
from datetime import datetime, timezone
from pathlib import Path

import requests

from tools.blender_engine import blender_available, blender_status, build_with_blender

MAC_AGENT_URL = os.environ.get("MAC_AGENT_URL", "http://localhost:8765")

# Default workshop root (created on demand). Override with WORKSHOP_DIR.
_DEFAULT_WORKSHOP = Path.home() / "Desktop" / "JARVIS" / "workshop"


def workshop_dir() -> Path:
    raw = os.environ.get("WORKSHOP_DIR", "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return _DEFAULT_WORKSHOP.resolve()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (name or "model").strip())
    s = s.strip("._-") or "model"
    return s[:60]


def _ensure_under_workshop(path: Path) -> tuple[Path | None, str | None]:
    root = workshop_dir()
    try:
        path = path.resolve()
        path.relative_to(root)
    except ValueError:
        return None, f"path {path} is outside workshop root {root}"
    except OSError as exc:
        return None, f"invalid path: {exc}"
    return path, None


# --- Mesh primitives (triangle soup) ---------------------------------------

Vec3 = tuple[float, float, float]
Tri = tuple[Vec3, Vec3, Vec3]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _normal(t: Tri) -> Vec3:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / length, ny / length, nz / length)


def _box_mesh(cx: float, cy: float, cz: float, sx: float, sy: float, sz: float) -> list[Tri]:
    """Axis-aligned box centered at (cx,cy,cz) with full sizes sx,sy,sz."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    # 8 corners
    def c(i, j, k):
        return (cx + i * hx, cy + j * hy, cz + k * hz)

    v = {
        "nwl": c(-1, -1, -1),
        "nwr": c(1, -1, -1),
        "nel": c(-1, 1, -1),
        "ner": c(1, 1, -1),
        "fwl": c(-1, -1, 1),
        "fwr": c(1, -1, 1),
        "fel": c(-1, 1, 1),
        "fer": c(1, 1, 1),
    }
    faces = [
        # -Z
        (v["nwl"], v["nel"], v["ner"]),
        (v["nwl"], v["ner"], v["nwr"]),
        # +Z
        (v["fwl"], v["fwr"], v["fer"]),
        (v["fwl"], v["fer"], v["fel"]),
        # -Y
        (v["nwl"], v["nwr"], v["fwr"]),
        (v["nwl"], v["fwr"], v["fwl"]),
        # +Y
        (v["nel"], v["fel"], v["fer"]),
        (v["nel"], v["fer"], v["ner"]),
        # -X
        (v["nwl"], v["fwl"], v["fel"]),
        (v["nwl"], v["fel"], v["nel"]),
        # +X
        (v["nwr"], v["ner"], v["fer"]),
        (v["nwr"], v["fer"], v["fwr"]),
    ]
    return faces


def _cylinder_mesh(
    cx: float,
    cy: float,
    cz: float,
    radius: float,
    height: float,
    axis: str = "z",
    segments: int = 24,
) -> list[Tri]:
    """Cylinder centered at origin of its body, then translated to cx,cy,cz.

    axis: which axis the cylinder runs along ('x','y','z').
    """
    segs = max(8, min(int(segments), 64))
    tris: list[Tri] = []
    h = height / 2
    axis = (axis or "z").lower()

    def point(i: int, z: float) -> Vec3:
        a = 2 * math.pi * i / segs
        x, y = radius * math.cos(a), radius * math.sin(a)
        if axis == "x":
            return (z, x, y)
        if axis == "y":
            return (x, z, y)
        return (x, y, z)

    top = [point(i, h) for i in range(segs)]
    bot = [point(i, -h) for i in range(segs)]
    center_top = (0.0, 0.0, h) if axis == "z" else (
        (h, 0.0, 0.0) if axis == "x" else (0.0, h, 0.0)
    )
    center_bot = (0.0, 0.0, -h) if axis == "z" else (
        (-h, 0.0, 0.0) if axis == "x" else (0.0, -h, 0.0)
    )

    for i in range(segs):
        j = (i + 1) % segs
        # side
        tris.append((bot[i], bot[j], top[j]))
        tris.append((bot[i], top[j], top[i]))
        # caps
        tris.append((center_top, top[i], top[j]))
        tris.append((center_bot, bot[j], bot[i]))

    # translate
    origin = (cx, cy, cz)
    return [(_add(a, origin), _add(b, origin), _add(c, origin)) for a, b, c in tris]


def _sphere_mesh(cx: float, cy: float, cz: float, radius: float, segments: int = 16) -> list[Tri]:
    segs = max(8, min(int(segments), 32))
    tris: list[Tri] = []
    # UV sphere
    def sph(u: int, v: int) -> Vec3:
        theta = math.pi * v / segs  # 0..pi
        phi = 2 * math.pi * u / segs
        x = radius * math.sin(theta) * math.cos(phi)
        y = radius * math.sin(theta) * math.sin(phi)
        z = radius * math.cos(theta)
        return (cx + x, cy + y, cz + z)

    for v in range(segs):
        for u in range(segs):
            p00 = sph(u, v)
            p10 = sph(u + 1, v)
            p01 = sph(u, v + 1)
            p11 = sph(u + 1, v + 1)
            if v != 0:
                tris.append((p00, p01, p11))
            if v != segs - 1:
                tris.append((p00, p11, p10))
    return tris


def _cone_mesh(
    cx: float, cy: float, cz: float, radius: float, height: float, segments: int = 24
) -> list[Tri]:
    segs = max(8, min(int(segments), 64))
    tris: list[Tri] = []
    h = height / 2
    apex = (cx, cy, cz + h)
    base_c = (cx, cy, cz - h)
    base = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        base.append((cx + radius * math.cos(a), cy + radius * math.sin(a), cz - h))
    for i in range(segs):
        j = (i + 1) % segs
        tris.append((apex, base[i], base[j]))
        tris.append((base_c, base[j], base[i]))
    return tris


def _part_to_mesh(part: dict) -> list[Tri]:
    ptype = str(part.get("type", "box")).lower().strip()
    pos = part.get("pos") or part.get("position") or [0, 0, 0]
    if not isinstance(pos, (list, tuple)) or len(pos) != 3:
        pos = [0, 0, 0]
    cx, cy, cz = float(pos[0]), float(pos[1]), float(pos[2])

    if ptype == "box":
        size = part.get("size") or [10, 10, 10]
        if not isinstance(size, (list, tuple)) or len(size) != 3:
            size = [10, 10, 10]
        return _box_mesh(cx, cy, cz, float(size[0]), float(size[1]), float(size[2]))

    if ptype == "cylinder":
        r = float(part.get("radius", 5))
        h = float(part.get("height", 10))
        axis = str(part.get("axis", "z"))
        segs = int(part.get("segments", 24))
        return _cylinder_mesh(cx, cy, cz, r, h, axis=axis, segments=segs)

    if ptype == "sphere":
        r = float(part.get("radius", 5))
        segs = int(part.get("segments", 16))
        return _sphere_mesh(cx, cy, cz, r, segments=segs)

    if ptype == "cone":
        r = float(part.get("radius", 5))
        h = float(part.get("height", 10))
        segs = int(part.get("segments", 24))
        return _cone_mesh(cx, cy, cz, r, h, segments=segs)

    # unknown → small marker box so we don't fail the whole assembly
    return _box_mesh(cx, cy, cz, 2, 2, 2)


def write_binary_stl(path: Path, triangles: list[Tri], solid_name: str = "jarvis") -> None:
    """Write a binary STL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = solid_name.encode("ascii", errors="replace")[:80].ljust(80, b"\0")
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            nx, ny, nz = _normal(tri)
            f.write(struct.pack("<3f", nx, ny, nz))
            for v in tri:
                f.write(struct.pack("<3f", float(v[0]), float(v[1]), float(v[2])))
            f.write(struct.pack("<H", 0))


# --- Public tools ----------------------------------------------------------

def workshop_engines() -> dict:
    """Report which model engines are available."""
    b = blender_status()
    return {
        "ok": True,
        "engines": {
            "primitives": {"available": True, "desc": "Always-on pure-Python STL"},
            "blender": {
                "available": b.get("available"),
                "bin": b.get("blender_bin"),
                "desc": "Named/colorized .blend + STL + GLB",
            },
        },
        "default": "auto (blender if installed, else primitives)",
        "hint": b.get("hint"),
    }


def _build_primitives(
    project: Path,
    slug: str,
    title: str,
    parts: list,
    units: str,
    notes: str | None,
) -> dict:
    tris: list[Tri] = []
    catalog = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            return {"ok": False, "error": f"part {i} is not an object"}
        mesh = _part_to_mesh(part)
        tris.extend(mesh)
        catalog.append(
            {
                "index": i,
                "name": part.get("name") or f"part_{i}",
                "type": part.get("type", "box"),
                "pos": part.get("pos") or part.get("position") or [0, 0, 0],
                "triangles": len(mesh),
            }
        )

    if not tris:
        return {"ok": False, "error": "no geometry produced"}

    stl_path = project / f"{slug}.stl"
    write_binary_stl(stl_path, tris, solid_name=slug)

    meta = {
        "name": slug,
        "title": title,
        "engine": "primitives",
        "units": units,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "part_count": len(catalog),
        "triangle_count": len(tris),
        "parts": catalog,
        "stl": str(stl_path),
        "notes": notes or "",
    }
    meta_path = project / "model.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if notes:
        (project / "BRIEF.md").write_text(
            f"# {title}\n\n{notes}\n",
            encoding="utf-8",
        )

    return {
        "ok": True,
        "engine": "primitives",
        "project_dir": str(project),
        "stl_path": str(stl_path),
        "blend_path": None,
        "glb_path": None,
        "meta_path": str(meta_path),
        "part_count": len(catalog),
        "triangle_count": len(tris),
        "units": units,
        "result": (
            f"Built primitive STL '{title}' with {len(catalog)} parts "
            f"({len(tris)} tris) at {stl_path}. "
            "Open with eDrawings/Preview via open_file, or reveal_in_finder."
        ),
    }


def build_3d_model(
    name: str,
    parts: list,
    title: str | None = None,
    units: str = "cm",
    notes: str | None = None,
    engine: str = "auto",
    open_after: bool = False,
) -> dict:
    """Assemble parts into a workshop 3D model.

    Each part is a dict, e.g.:
      {"type":"box","name":"radiator","size":[40,2,20],"pos":[0,15,0],
       "color":[0.9,0.3,0.2]}
      {"type":"cylinder","name":"tank","radius":6,"height":18,"pos":[0,0,0]}
      {"type":"sphere","name":"sensor","radius":2,"pos":[10,0,8]}
      {"type":"cone","name":"nozzle","radius":3,"height":8,"pos":[0,-12,0]}

    engine:
      - auto (default): Blender if installed, else primitives
      - blender: require Blender (colorized .blend + STL + GLB)
      - primitives: pure-Python STL only

    Coordinate system: X right, Y up, Z toward viewer. Units are labels.
    """
    if not parts or not isinstance(parts, list):
        return {"ok": False, "error": "parts must be a non-empty list of part dicts"}

    if len(parts) > 80:
        return {"ok": False, "error": "too many parts (max 80) — simplify the assembly"}

    eng = (engine or "auto").strip().lower()
    if eng not in ("auto", "blender", "primitives"):
        return {"ok": False, "error": f"engine must be auto|blender|primitives, got {engine!r}"}

    use_blender = eng == "blender" or (eng == "auto" and blender_available())
    if eng == "blender" and not blender_available():
        eng_info = workshop_engines()
        return {
            "ok": False,
            "error": (
                "engine=blender requested but Blender is not installed. "
                "Install from blender.org into /Applications, or use engine=primitives / auto."
            ),
            "engines": eng_info.get("engines"),
            "hint": eng_info.get("hint"),
        }

    slug = _slug(name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project = workshop_dir() / f"{slug}_{stamp}"
    project.mkdir(parents=True, exist_ok=True)
    display_title = title or name

    if use_blender:
        bl = build_with_blender(
            project=project,
            slug=slug,
            title=display_title,
            parts=parts,
            units=units,
        )
        if not bl.get("ok"):
            # auto falls back to primitives; hard blender request does not
            if eng == "auto":
                prim = _build_primitives(
                    project, slug, display_title, parts, units, notes
                )
                if prim.get("ok"):
                    prim["blender_fallback_error"] = bl.get("error")
                    prim["result"] = (
                        f"(Blender failed → primitives) {prim.get('result')} "
                        f"Blender error: {bl.get('error')}"
                    )
                return prim
            return bl

        meta = {
            "name": slug,
            "title": display_title,
            "engine": "blender",
            "units": units,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "part_count": bl.get("part_count"),
            "parts": bl.get("parts"),
            "stl": bl.get("stl_path"),
            "blend": bl.get("blend_path"),
            "glb": bl.get("glb_path"),
            "notes": notes or "",
        }
        meta_path = project / "model.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        if notes:
            (project / "BRIEF.md").write_text(
                f"# {display_title}\n\n{notes}\n",
                encoding="utf-8",
            )

        blend = bl.get("blend_path")
        stl = bl.get("stl_path")
        result = {
            "ok": True,
            "engine": "blender",
            "project_dir": str(project),
            "stl_path": stl,
            "blend_path": blend,
            "glb_path": bl.get("glb_path"),
            "meta_path": str(meta_path),
            "part_count": bl.get("part_count"),
            "units": units,
            "result": (
                f"Built Blender model '{display_title}' with {bl.get('part_count')} "
                f"named/colorized parts. "
                f"Open blend in Blender: {blend}. STL: {stl}. "
                "Prefer open_file(path=blend_path, app_name='Blender') so you can "
                "spin the color-coded assembly while explaining parts by name."
            ),
        }
        if open_after and blend:
            opened = open_file(blend, app_name="Blender")
            result["opened"] = opened
        return result

    return _build_primitives(project, slug, display_title, parts, units, notes)


def write_design_brief(
    name: str,
    content: str,
    project_dir: str | None = None,
) -> dict:
    """Write a markdown design brief into a workshop project folder.

    If project_dir is omitted, creates a new folder under the workshop root.
    """
    content = (content or "").strip()
    if not content:
        return {"ok": False, "error": "content is empty"}

    if project_dir:
        p, err = _ensure_under_workshop(Path(os.path.expanduser(project_dir)))
        if err:
            return {"ok": False, "error": err}
        assert p is not None
        p.mkdir(parents=True, exist_ok=True)
        target = p
    else:
        slug = _slug(name)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = workshop_dir() / f"{slug}_{stamp}"
        target.mkdir(parents=True, exist_ok=True)

    path = target / "BRIEF.md"
    title = name.strip() or "Design brief"
    body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}\n"
    path.write_text(body, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "project_dir": str(target),
        "result": f"Wrote design brief to {path}",
    }


def open_file(path: str, app_name: str | None = None) -> dict:
    """Open a file on the Mac via the mac agent (workshop allowlist enforced there too).

    Prefer app_name='eDrawings' for STL if installed; omit to use default handler.
    """
    try:
        payload: dict = {"path": path}
        if app_name:
            payload["app_name"] = app_name
        resp = requests.post(
            f"{MAC_AGENT_URL}/open_path",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Mac agent offline — start mac_agent on port 8765",
        }
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def reveal_in_finder(path: str) -> dict:
    """Reveal a workshop file/folder in Finder via the mac agent."""
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/reveal_in_finder",
            json={"path": path},
            timeout=12,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Mac agent offline — start mac_agent on port 8765",
        }
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
