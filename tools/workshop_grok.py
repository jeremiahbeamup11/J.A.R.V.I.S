"""
High-fidelity 3D design via Grok Build (not Claude primitives).

Flow:
  1. Create a workshop project folder (under GROK allowlist).
  2. Seed a Blender script scaffold + DESIGN_BRIEF.md.
  3. Run Grok Build to author a real bpy scene (geometry, materials, names).
  4. Execute that script headlessly in Blender → .blend / .stl / .glb.
  5. Optionally open the .blend on the Mac.

This is stronger than template primitives when the user wants something that
actually *looks* like a thermal system / lander / mechanism.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools.blender_engine import find_blender
from tools.grok_build import resolve_project_path, run_grok_build
from tools.workshop import open_file, workshop_dir

_SCRIPT_CANDIDATES = (
    "build_scene.py",
    "blender_scene.py",
    "model_scene.py",
    "build_model.py",
    "_grok_blender_model.py",
)

_SCAFFOLD = '''\
"""
Jarvis / Grok Build — Blender scene script.
Run headless: Blender --background --python build_scene.py

Grok: replace this scaffold with a full, readable engineering model.
Requirements:
  - Clear object names (e.g. propellant_tank, radiator_port, heat_pipe_01)
  - Distinct materials/colors per subsystem
  - Realistic relative proportions (not 4 toy primitives)
  - Save model.blend, export model.stl and model.glb next to this file
  - Write LEGEND.md describing each major part
"""
from pathlib import Path
import math
import bpy

ROOT = Path(__file__).resolve().parent
BLEND = ROOT / "model.blend"
STL = ROOT / "model.stl"
GLB = ROOT / "model.glb"


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def mat(name, rgb, metallic=0.2, roughness=0.4):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
    return m


def apply_mat(obj, material):
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def main():
    reset_scene()
    # --- Grok: build the real assembly below this line ---
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = "PLACEHOLDER_replace_me"
    apply_mat(obj, mat("placeholder", (0.5, 0.5, 0.5)))

    # Camera + light
    bpy.ops.object.light_add(type="SUN", location=(20, -20, 40))
    bpy.ops.object.camera_add(location=(40, -40, 30))
    cam = bpy.context.active_object
    cam.rotation_euler = (math.radians(60), 0, math.radians(45))
    bpy.context.scene.camera = cam

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH")
    try:
        bpy.ops.wm.stl_export(filepath=str(STL), export_selected_objects=True)
    except Exception:
        try:
            bpy.ops.export_mesh.stl(filepath=str(STL), use_selection=True)
        except Exception:
            pass
    try:
        bpy.ops.export_scene.gltf(filepath=str(GLB), export_format="GLB")
    except Exception:
        pass


if __name__ == "__main__":
    main()
'''


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (name or "design").strip())
    return (s.strip("._-") or "design")[:60]


def _find_scene_script(project: Path) -> Path | None:
    for name in _SCRIPT_CANDIDATES:
        p = project / name
        if p.is_file() and p.stat().st_size > 50:
            return p
    # any *scene*.py or *blender*.py Grok might create
    for p in sorted(project.glob("*.py")):
        if p.name.startswith("_jarvis"):
            continue
        low = p.name.lower()
        if any(k in low for k in ("scene", "blender", "model", "build")):
            return p
    # fallback: build_scene.py even if still scaffold
    cand = project / "build_scene.py"
    return cand if cand.is_file() else None


def _run_blender_script(script: Path, timeout: int = 300) -> dict:
    blender = find_blender()
    if not blender:
        return {
            "ok": False,
            "error": "Blender not found — install Blender.app or set BLENDER_BIN",
        }
    try:
        proc = subprocess.run(
            [blender, "--background", "--python", str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script.parent),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Blender timed out after {timeout}s"}
    except FileNotFoundError:
        return {"ok": False, "error": f"failed to execute Blender at {blender}"}

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "blender_bin": blender,
    }


def design_3d_with_grok(
    description: str,
    name: str,
    title: str | None = None,
    open_after: bool = True,
    continue_session: bool = True,
    new_session: bool = False,
    max_turns: int | None = None,
) -> dict:
    """Have Grok Build author a Blender scene, then execute it headlessly.

    Args:
        description: What to design (engineering requirements + visual intent).
        name: Project slug under workshop/.
        title: Human title.
        open_after: Open model.blend in Blender when done.
        continue_session: Resume Grok session for multi-step design refinement.
        new_session: Force a fresh Grok design session.
        max_turns: Cap Grok agent turns (default env / higher for design).
    """
    description = (description or "").strip()
    if not description:
        return {"ok": False, "error": "description is empty"}

    slug = _slug(name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project = workshop_dir() / f"{slug}_{stamp}"
    project.mkdir(parents=True, exist_ok=True)

    # Must be under Grok allowlist (Desktop includes workshop)
    path, err = resolve_project_path(str(project))
    if err:
        return {
            "ok": False,
            "error": (
                f"Workshop project not on GROK_BUILD_ALLOWLIST: {err}. "
                "Ensure GROK_BUILD_ALLOWLIST includes ~/Desktop (or your workshop root)."
            ),
            "project_dir": str(project),
        }
    project = path  # resolved

    display_title = title or name or slug
    brief_path = project / "DESIGN_BRIEF.md"
    script_path = project / "build_scene.py"
    legend_path = project / "LEGEND.md"

    brief_path.write_text(
        f"# {display_title}\n\n"
        f"## User request\n\n{description}\n\n"
        f"## Goal\n\n"
        f"Produce a **high-fidelity schematic / concept model** in Blender that "
        f"reads as a real engineering system (subsystems, proportions, named parts), "
        f"**not** a handful of random primitives.\n",
        encoding="utf-8",
    )
    script_path.write_text(_SCAFFOLD, encoding="utf-8")

    turns = max_turns
    if turns is None:
        turns = int(os.environ.get("GROK_DESIGN_MAX_TURNS", "50") or "50")

    grok_task = f"""
You are designing a 3D engineering concept model for Jarvis.

## Project directory (cwd)
{project}

## Design request
{description}

## Title
{display_title}

## Your job
1. Read DESIGN_BRIEF.md and the scaffold build_scene.py.
2. Rewrite build_scene.py into a **complete Blender (bpy) scene** that models the system.
3. Requirements for the model:
   - Named objects for every major subsystem (clear English names).
   - Distinct materials/colors per subsystem (tank, radiator, heat pipes, structure, avionics, propulsion, sensors).
   - **At least 12 meaningful mesh objects** for a full system; more if needed.
   - Realistic relative proportions and spatial layout (assemblies, not a pile of toys).
   - For thermal systems: tank + insulation indication + cold plate + multiple heat pipes + radiator area + structure + sensors.
   - For landers: body, tanks, legs/footpads, thrusters, radiators, antenna as appropriate.
4. build_scene.py must:
   - Clear/reset the scene
   - Build the geometry
   - Add a sun light + camera framed on the model
   - Save **model.blend** in this directory
   - Export **model.stl** and **model.glb** if possible
5. Write **LEGEND.md** listing each major part and its engineering role.
6. Do not leave PLACEHOLDER_replace_me in the final scene.
7. Keep everything inside this project directory only.

When done, summarize what subsystems you modeled and the file paths.
""".strip()

    grok_result = run_grok_build(
        task=grok_task,
        project_path=str(project),
        mode="build",
        max_turns=turns,
        continue_session=continue_session,
        new_session=new_session,
    )

    if not grok_result.get("ok"):
        return {
            "ok": False,
            "error": grok_result.get("error") or "Grok Build failed",
            "project_dir": str(project),
            "grok": {
                "text": (grok_result.get("text") or "")[:2000],
                "session_id": grok_result.get("session_id"),
                "session_mode": grok_result.get("session_mode"),
            },
            "result": (
                "Grok Build did not finish successfully. "
                f"Details: {grok_result.get('error') or grok_result.get('text') or 'unknown'}"
            ),
        }

    scene_script = _find_scene_script(project)
    if not scene_script:
        return {
            "ok": False,
            "error": "Grok finished but no Blender scene script was found (expected build_scene.py)",
            "project_dir": str(project),
            "grok_text": (grok_result.get("text") or "")[:1500],
        }

    # Reject pure scaffold if Grok didn't really edit
    script_text = scene_script.read_text(encoding="utf-8", errors="replace")
    if "PLACEHOLDER_replace_me" in script_text and script_text.count("primitive_") < 4:
        return {
            "ok": False,
            "error": (
                "Grok left the placeholder scaffold mostly unchanged. "
                "Retry design_3d_with_grok with continue_session=true and a more specific description."
            ),
            "project_dir": str(project),
            "script": str(scene_script),
            "grok_text": (grok_result.get("text") or "")[:1500],
        }

    blender_run = _run_blender_script(scene_script)
    blend = project / "model.blend"
    stl = project / "model.stl"
    glb = project / "model.glb"

    # If Grok saved alternate names, pick them up
    if not blend.exists():
        alts = list(project.glob("*.blend"))
        if alts:
            blend = alts[0]
    if not stl.exists():
        alts = list(project.glob("*.stl"))
        if alts:
            stl = alts[0]

    ok_files = blend.exists() or stl.exists()
    if not blender_run.get("ok") and not ok_files:
        return {
            "ok": False,
            "error": "Blender failed to execute Grok's scene script",
            "project_dir": str(project),
            "script": str(scene_script),
            "blender": blender_run,
            "grok_text": (grok_result.get("text") or "")[:1500],
        }

    meta = {
        "name": slug,
        "title": display_title,
        "engine": "grok_blender",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "script": str(scene_script),
        "blend": str(blend) if blend.exists() else None,
        "stl": str(stl) if stl.exists() else None,
        "glb": str(glb) if glb.exists() else None,
        "grok_session_id": grok_result.get("session_id"),
        "legend_path": str(legend_path) if legend_path.exists() else None,
    }
    (project / "model.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    opened = None
    if open_after and blend.exists():
        opened = open_file(str(blend), app_name="Blender")

    legend_preview = ""
    if legend_path.exists():
        legend_preview = legend_path.read_text(encoding="utf-8", errors="replace")[:2500]

    summary = (grok_result.get("text") or "").strip()
    if len(summary) > 1500:
        summary = summary[:1500] + "…"

    return {
        "ok": True,
        "engine": "grok_blender",
        "project_dir": str(project),
        "blend_path": str(blend) if blend.exists() else None,
        "stl_path": str(stl) if stl.exists() else None,
        "glb_path": str(glb) if glb.exists() else None,
        "script_path": str(scene_script),
        "legend_path": str(legend_path) if legend_path.exists() else None,
        "legend_preview": legend_preview,
        "grok_session_id": grok_result.get("session_id"),
        "continued": grok_result.get("continued"),
        "opened": opened,
        "blender_run_ok": blender_run.get("ok"),
        "result": (
            f"Grok Build authored a Blender scene for '{display_title}'. "
            f"blend={blend if blend.exists() else 'n/a'} "
            f"script={scene_script.name}. "
            "Explain the system using LEGEND.md and named objects in the scene. "
            + (f"Grok summary: {summary}" if summary else "")
        ),
    }
