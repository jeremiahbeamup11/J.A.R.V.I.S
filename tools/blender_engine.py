"""
Blender backend for Jarvis Workshop (Milestone 11b).

When Blender is installed, Jarvis can build named/colorized assemblies as:
  - .blend (open in Blender)
  - .stl   (eDrawings / slicers)
  - .glb   (web/preview friendly)

Runs headless only:
  Blender --background --python <script> -- <json_spec_path>

No arbitrary user Python is executed — only our generated script + a
JSON parts spec written under the workshop project folder.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# Palette cycled by part index when color not provided (sRGB 0–1).
_DEFAULT_COLORS = [
    (0.85, 0.25, 0.20),  # red-ish
    (0.20, 0.55, 0.90),  # blue
    (0.25, 0.75, 0.40),  # green
    (0.95, 0.70, 0.15),  # amber
    (0.65, 0.40, 0.90),  # purple
    (0.20, 0.80, 0.80),  # cyan
    (0.90, 0.50, 0.20),  # orange
    (0.70, 0.70, 0.75),  # gray
]


def find_blender() -> str | None:
    """Locate Blender binary. Override with BLENDER_BIN."""
    env = os.environ.get("BLENDER_BIN", "").strip()
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env

    candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.2.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.3.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.4.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
        "/Applications/Blender 5.0.app/Contents/MacOS/Blender",
        str(Path.home() / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    which = shutil.which("blender")
    if which:
        return which
    return None


def blender_available() -> bool:
    return find_blender() is not None


def blender_status() -> dict:
    path = find_blender()
    return {
        "ok": True,
        "available": path is not None,
        "blender_bin": path,
        "hint": (
            "Blender ready for engine=blender / auto"
            if path
            else (
                "Install Blender from https://www.blender.org/download/ "
                "(drag Blender.app to /Applications). Optional: set BLENDER_BIN."
            )
        ),
    }


# Script run inside Blender — kept as a string constant (not user-supplied).
_BLENDER_SCRIPT = r'''
import json
import math
import sys
from pathlib import Path

import bpy

# argv after "--"
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

if not argv:
    raise SystemExit("missing spec path argument")

spec_path = Path(argv[0])
spec = json.loads(spec_path.read_text(encoding="utf-8"))

out_blend = Path(spec["out_blend"])
out_stl = Path(spec["out_stl"])
out_glb = Path(spec.get("out_glb") or "")
parts = spec.get("parts") or []
title = spec.get("title") or "Jarvis Model"

# Fresh scene
bpy.ops.wm.read_factory_settings(use_empty=True)
# Remove default objects if any remain
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

def ensure_material(name, rgb):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.45
    return mat

def set_origin_to_geometry(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.select_set(False)

created = []
for i, part in enumerate(parts):
    ptype = str(part.get("type", "box")).lower()
    name = str(part.get("name") or f"part_{i}")[:60]
    pos = part.get("pos") or part.get("position") or [0, 0, 0]
    if not isinstance(pos, (list, tuple)) or len(pos) != 3:
        pos = [0, 0, 0]
    cx, cy, cz = float(pos[0]), float(pos[1]), float(pos[2])
    color = part.get("color") or part.get("rgb")
    if not (isinstance(color, (list, tuple)) and len(color) >= 3):
        palette = spec.get("palette") or []
        color = palette[i % len(palette)] if palette else [0.7, 0.7, 0.7]
    rgb = (float(color[0]), float(color[1]), float(color[2]))

    obj = None
    if ptype == "box":
        size = part.get("size") or [10, 10, 10]
        sx, sy, sz = float(size[0]), float(size[1]), float(size[2])
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz))
        obj = bpy.context.active_object
        obj.scale = (sx / 2.0, sy / 2.0, sz / 2.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    elif ptype == "cylinder":
        r = float(part.get("radius", 5))
        h = float(part.get("height", 10))
        axis = str(part.get("axis", "z")).lower()
        segs = max(8, min(int(part.get("segments", 32)), 64))
        bpy.ops.mesh.primitive_cylinder_add(
            radius=r, depth=h, vertices=segs, location=(cx, cy, cz)
        )
        obj = bpy.context.active_object
        if axis == "x":
            obj.rotation_euler = (0.0, math.radians(90), 0.0)
        elif axis == "y":
            obj.rotation_euler = (math.radians(90), 0.0, 0.0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    elif ptype == "sphere":
        r = float(part.get("radius", 5))
        segs = max(8, min(int(part.get("segments", 24)), 64))
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=r, segments=segs, ring_count=max(8, segs // 2), location=(cx, cy, cz)
        )
        obj = bpy.context.active_object
    elif ptype == "cone":
        r = float(part.get("radius", 5))
        h = float(part.get("height", 10))
        segs = max(8, min(int(part.get("segments", 32)), 64))
        bpy.ops.mesh.primitive_cone_add(
            radius1=r, radius2=0.0, depth=h, vertices=segs, location=(cx, cy, cz)
        )
        obj = bpy.context.active_object
    else:
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(cx, cy, cz))
        obj = bpy.context.active_object

    if obj is None:
        continue
    obj.name = name
    mat = ensure_material(f"mat_{name}", rgb)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    created.append({"name": obj.name, "type": ptype})

# Simple camera + light for nicer .blend open experience
bpy.ops.object.light_add(type="SUN", location=(20, -20, 40))
bpy.ops.object.camera_add(location=(45, -45, 35))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(60), 0.0, math.radians(45))
bpy.context.scene.camera = cam

# Collection name
if created:
    coll = bpy.data.collections.new(title[:60] or "Jarvis")
    bpy.context.scene.collection.children.link(coll)

out_blend.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))

# Export STL (all meshes)
for obj in bpy.data.objects:
    obj.select_set(obj.type == "MESH")
try:
    bpy.ops.export_mesh.stl(filepath=str(out_stl), use_selection=True)
except Exception:
    # Blender 4+ may use different operator
    try:
        bpy.ops.wm.stl_export(filepath=str(out_stl), export_selected_objects=True)
    except Exception as exc:
        print("STL_EXPORT_FAIL", exc)

# Export glTF/GLB
if out_glb:
    try:
        bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB")
    except Exception as exc:
        print("GLB_EXPORT_FAIL", exc)

result = {
    "ok": True,
    "parts_created": len(created),
    "created": created,
    "blend": str(out_blend),
    "stl": str(out_stl),
    "glb": str(out_glb) if out_glb else None,
}
print("JARVIS_BLENDER_RESULT=" + json.dumps(result))
'''


def build_with_blender(
    project: Path,
    slug: str,
    title: str,
    parts: list,
    units: str = "cm",
) -> dict:
    """Create .blend / .stl / .glb via headless Blender from parts list."""
    blender = find_blender()
    if not blender:
        return {
            "ok": False,
            "error": "Blender not found. Install Blender.app to /Applications or set BLENDER_BIN.",
        }

    project = Path(project)
    project.mkdir(parents=True, exist_ok=True)

    # Normalize parts + assign colors
    norm_parts = []
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            return {"ok": False, "error": f"part {i} is not an object"}
        p = dict(part)
        if not p.get("color") and not p.get("rgb"):
            p["color"] = list(_DEFAULT_COLORS[i % len(_DEFAULT_COLORS)])
        norm_parts.append(p)

    out_blend = project / f"{slug}.blend"
    out_stl = project / f"{slug}.stl"
    out_glb = project / f"{slug}.glb"
    script_path = project / "_jarvis_blender_build.py"
    spec_path = project / "_jarvis_blender_spec.json"

    spec = {
        "title": title,
        "units": units,
        "parts": norm_parts,
        "palette": [list(c) for c in _DEFAULT_COLORS],
        "out_blend": str(out_blend),
        "out_stl": str(out_stl),
        "out_glb": str(out_glb),
    }
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    script_path.write_text(_BLENDER_SCRIPT, encoding="utf-8")

    timeout = int(os.environ.get("BLENDER_TIMEOUT_SEC", "180") or "180")
    cmd = [
        blender,
        "--background",
        "--python",
        str(script_path),
        "--",
        str(spec_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "BLENDER_SYSTEM_PYTHON": ""},
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Blender timed out after {timeout}s",
            "project_dir": str(project),
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"failed to execute Blender at {blender}"}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    parsed = None
    for line in stdout.splitlines():
        if line.startswith("JARVIS_BLENDER_RESULT="):
            try:
                parsed = json.loads(line.split("=", 1)[1])
            except json.JSONDecodeError:
                pass

    if proc.returncode != 0 and not out_blend.exists():
        return {
            "ok": False,
            "error": (stderr or stdout or f"Blender exited {proc.returncode}")[:2000],
            "exit_code": proc.returncode,
            "project_dir": str(project),
        }

    # Prefer files on disk over parsed message
    ok_files = out_blend.exists() or out_stl.exists()
    if not ok_files:
        return {
            "ok": False,
            "error": "Blender finished but produced no .blend/.stl",
            "stdout_tail": stdout[-1500:],
            "stderr_tail": stderr[-1500:],
            "project_dir": str(project),
        }

    catalog = []
    for i, p in enumerate(norm_parts):
        catalog.append(
            {
                "index": i,
                "name": p.get("name") or f"part_{i}",
                "type": p.get("type", "box"),
                "pos": p.get("pos") or p.get("position") or [0, 0, 0],
                "color": p.get("color"),
            }
        )

    return {
        "ok": True,
        "engine": "blender",
        "blender_bin": blender,
        "project_dir": str(project),
        "blend_path": str(out_blend) if out_blend.exists() else None,
        "stl_path": str(out_stl) if out_stl.exists() else None,
        "glb_path": str(out_glb) if out_glb.exists() else None,
        "part_count": len(catalog),
        "parts": catalog,
        "blender_report": parsed,
        "exit_code": proc.returncode,
    }
