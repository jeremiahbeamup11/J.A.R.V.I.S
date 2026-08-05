"""
Workshop system templates — structured assemblies, not random primitives.

Claude (or the user) picks a template; we expand it into a full named,
color-coded part list with engineering-ish layout. Optional scale + a few
knobs keep models readable without free-form under-building.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Colors (sRGB 0–1) — stable legend for explanations
C = {
    "tank": [0.20, 0.50, 0.90],       # blue — fluids / tanks
    "radiator": [0.90, 0.25, 0.18],   # red — heat rejection
    "heat_pipe": [0.95, 0.75, 0.15],  # gold — thermal transport
    "cold_plate": [0.25, 0.80, 0.85], # cyan — pickup
    "structure": [0.55, 0.58, 0.62],  # gray — structure
    "avionics": [0.30, 0.75, 0.35],   # green — electronics
    "propulsion": [0.95, 0.55, 0.15], # orange — engines
    "insulation": [0.75, 0.75, 0.80], # light gray — MLI
    "sensor": [0.70, 0.35, 0.90],     # purple — sensors
    "leg": [0.45, 0.45, 0.50],
}


def list_templates() -> dict:
    """Public catalog for tools / API."""
    return {
        "ok": True,
        "templates": {
            "lunar_thermal": {
                "desc": (
                    "Lunar hopper thermal architecture: propellant tank, cold plate, "
                    "heat pipes, dual radiator panels, MLI, avionics bay, sensors."
                ),
                "use_when": "thermal control, heat rejection, cooling on the Moon",
            },
            "hopper_lander": {
                "desc": (
                    "Full hopper lander schematic: body, tank, legs, thrusters, "
                    "radiators, avionics, antenna."
                ),
                "use_when": "whole vehicle / lander layout",
            },
            "propulsion": {
                "desc": "Propulsion stack: tanks, feed lines, engine, nozzle, mounts.",
                "use_when": "engines, thrust, propellant plumbing",
            },
            "electronics_bay": {
                "desc": "Avionics rack with cold plate, heat pipes, and small radiator.",
                "use_when": "avionics thermal / electronics packaging",
            },
        },
        "default_for_thermal": "lunar_thermal",
        "default_for_vehicle": "hopper_lander",
    }


def _scale_part(part: dict, s: float) -> dict:
    p = deepcopy(part)
    if "pos" in p:
        p["pos"] = [float(v) * s for v in p["pos"]]
    if "size" in p:
        p["size"] = [float(v) * s for v in p["size"]]
    for key in ("radius", "radius2", "height", "thickness", "length"):
        if key in p:
            p[key] = float(p[key]) * s
    return p


def _template_lunar_thermal(params: dict[str, Any]) -> list[dict]:
    """Schematic that reads as a thermal control system, not 4 toys."""
    pipes = int(params.get("heat_pipes", 4))
    pipes = max(2, min(pipes, 8))

    parts: list[dict] = [
        # Central propellant tank
        {
            "type": "cylinder",
            "name": "propellant_tank",
            "radius": 9,
            "height": 22,
            "pos": [0, 2, 0],
            "color": C["tank"],
            "role": "stores cryogenic / storable propellant; needs thermal isolation",
        },
        # MLI band around tank mid
        {
            "type": "torus",
            "name": "MLI_blanket_band",
            "radius": 10.5,
            "radius2": 1.2,
            "pos": [0, 2, 0],
            "color": C["insulation"],
            "role": "multi-layer insulation reducing radiative heat leak",
        },
        # Cold plate on tank shoulder (heat pickup)
        {
            "type": "box",
            "name": "cold_plate",
            "size": [12, 1.2, 10],
            "pos": [0, 14, 6],
            "color": C["cold_plate"],
            "role": "conducts heat from warm equipment into heat pipes",
        },
        # Avionics on cold plate
        {
            "type": "box",
            "name": "avionics_bay",
            "size": [10, 5, 8],
            "pos": [0, 17.5, 6],
            "color": C["avionics"],
            "role": "electronics heat source",
        },
        # Dual radiator panels (outboard, large area)
        {
            "type": "panel",
            "name": "radiator_port",
            "size": [22, 0.8, 16],
            "pos": [-18, 12, -4],
            "color": C["radiator"],
            "role": "radiates heat to deep space (port side)",
        },
        {
            "type": "panel",
            "name": "radiator_starboard",
            "size": [22, 0.8, 16],
            "pos": [18, 12, -4],
            "color": C["radiator"],
            "role": "radiates heat to deep space (starboard)",
        },
        # Structure spine
        {
            "type": "box",
            "name": "structure_spine",
            "size": [3, 20, 3],
            "pos": [0, 0, -8],
            "color": C["structure"],
            "role": "primary structure carrying loads and pipe runs",
        },
        # Sensors
        {
            "type": "sphere",
            "name": "temp_sensor_tank",
            "radius": 1.2,
            "pos": [8, 8, 4],
            "color": C["sensor"],
            "role": "tank wall temperature telemetry",
        },
        {
            "type": "sphere",
            "name": "temp_sensor_radiator",
            "radius": 1.2,
            "pos": [-18, 18, 4],
            "color": C["sensor"],
            "role": "radiator panel temperature telemetry",
        },
    ]

    # Heat pipes from cold plate region out to both radiators
    for i in range(pipes):
        t = (i / max(pipes - 1, 1)) - 0.5  # -0.5 .. 0.5
        y = 12 + t * 6
        # port-side pipe (along -X)
        parts.append(
            {
                "type": "pipe",
                "name": f"heat_pipe_port_{i+1}",
                "radius": 0.7,
                "height": 14,
                "axis": "x",
                "pos": [-9, y, 2 + t * 2],
                "color": C["heat_pipe"],
                "role": "two-phase heat transport tank/avionics → port radiator",
            }
        )
        # starboard pipe
        parts.append(
            {
                "type": "pipe",
                "name": f"heat_pipe_stbd_{i+1}",
                "radius": 0.7,
                "height": 14,
                "axis": "x",
                "pos": [9, y, 2 + t * 2],
                "color": C["heat_pipe"],
                "role": "two-phase heat transport tank/avionics → starboard radiator",
            }
        )

    return parts


def _template_hopper_lander(params: dict[str, Any]) -> list[dict]:
    parts: list[dict] = [
        {
            "type": "cylinder",
            "name": "fuselage_body",
            "radius": 11,
            "height": 14,
            "pos": [0, 6, 0],
            "color": C["structure"],
            "role": "primary lander body / bus",
        },
        {
            "type": "cylinder",
            "name": "propellant_tank",
            "radius": 7,
            "height": 12,
            "pos": [0, 8, 0],
            "color": C["tank"],
            "role": "main propellant",
        },
        {
            "type": "cone",
            "name": "main_engine_nozzle",
            "radius": 5,
            "height": 9,
            "pos": [0, -4, 0],
            "color": C["propulsion"],
            "role": "main descent / hop engine",
        },
        {
            "type": "box",
            "name": "avionics_bay",
            "size": [8, 4, 6],
            "pos": [0, 15, 6],
            "color": C["avionics"],
            "role": "flight computer / power electronics",
        },
        {
            "type": "panel",
            "name": "radiator_panel",
            "size": [18, 0.7, 12],
            "pos": [0, 14, -12],
            "color": C["radiator"],
            "role": "body-mounted radiator",
        },
        {
            "type": "pipe",
            "name": "heat_pipe_main",
            "radius": 0.8,
            "height": 10,
            "axis": "z",
            "pos": [0, 12, -6],
            "color": C["heat_pipe"],
            "role": "avionics heat to radiator",
        },
        {
            "type": "cylinder",
            "name": "comms_antenna_mast",
            "radius": 0.6,
            "height": 8,
            "pos": [0, 20, 0],
            "color": C["structure"],
            "role": "antenna mast",
        },
        {
            "type": "sphere",
            "name": "antenna_head",
            "radius": 2.2,
            "pos": [0, 25, 0],
            "color": C["sensor"],
            "role": "high-gain / omni antenna",
        },
    ]
    # Four landing legs
    for i, (x, z) in enumerate([(12, 12), (12, -12), (-12, 12), (-12, -12)]):
        parts.append(
            {
                "type": "leg",
                "name": f"landing_leg_{i+1}",
                "size": [2.2, 16, 2.2],
                "pos": [x, -2, z],
                "color": C["leg"],
                "role": "landing gear / hop leg",
            }
        )
        parts.append(
            {
                "type": "sphere",
                "name": f"footpad_{i+1}",
                "radius": 2.5,
                "pos": [x, -10, z],
                "color": C["structure"],
                "role": "footpad",
            }
        )
    # RCS pods
    for i, (x, z) in enumerate([(10, 0), (-10, 0), (0, 10), (0, -10)]):
        parts.append(
            {
                "type": "cylinder",
                "name": f"rcs_thruster_{i+1}",
                "radius": 1.5,
                "height": 3,
                "axis": "x" if abs(x) > abs(z) else "z",
                "pos": [x, 6, z],
                "color": C["propulsion"],
                "role": "attitude RCS thruster",
            }
        )
    return parts


def _template_propulsion(params: dict[str, Any]) -> list[dict]:
    return [
        {
            "type": "cylinder",
            "name": "fuel_tank",
            "radius": 7,
            "height": 14,
            "pos": [-8, 8, 0],
            "color": C["tank"],
            "role": "fuel tank",
        },
        {
            "type": "cylinder",
            "name": "oxidizer_tank",
            "radius": 7,
            "height": 14,
            "pos": [8, 8, 0],
            "color": [0.15, 0.35, 0.75],
            "role": "oxidizer tank",
        },
        {
            "type": "pipe",
            "name": "fuel_feed_line",
            "radius": 1.0,
            "height": 12,
            "axis": "y",
            "pos": [-8, 0, 0],
            "color": C["heat_pipe"],
            "role": "fuel feed",
        },
        {
            "type": "pipe",
            "name": "ox_feed_line",
            "radius": 1.0,
            "height": 12,
            "axis": "y",
            "pos": [8, 0, 0],
            "color": C["heat_pipe"],
            "role": "oxidizer feed",
        },
        {
            "type": "box",
            "name": "engine_mount",
            "size": [10, 3, 10],
            "pos": [0, -4, 0],
            "color": C["structure"],
            "role": "thrust structure",
        },
        {
            "type": "cylinder",
            "name": "combustion_chamber",
            "radius": 3.5,
            "height": 5,
            "pos": [0, -8, 0],
            "color": C["propulsion"],
            "role": "chamber",
        },
        {
            "type": "cone",
            "name": "nozzle",
            "radius": 7,
            "height": 12,
            "pos": [0, -16, 0],
            "color": C["propulsion"],
            "role": "expansion nozzle",
        },
        {
            "type": "sphere",
            "name": "pressure_transducer",
            "radius": 1.3,
            "pos": [0, -6, 5],
            "color": C["sensor"],
            "role": "chamber pressure sensor",
        },
    ]


def _template_electronics_bay(params: dict[str, Any]) -> list[dict]:
    return [
        {
            "type": "box",
            "name": "bay_enclosure",
            "size": [20, 12, 14],
            "pos": [0, 0, 0],
            "color": C["structure"],
            "role": "avionics enclosure",
        },
        {
            "type": "box",
            "name": "board_stack",
            "size": [12, 8, 8],
            "pos": [0, 0, 0],
            "color": C["avionics"],
            "role": "PCB stack heat source",
        },
        {
            "type": "box",
            "name": "cold_plate",
            "size": [14, 1, 10],
            "pos": [0, 5, 0],
            "color": C["cold_plate"],
            "role": "thermal interface plate",
        },
        {
            "type": "pipe",
            "name": "heat_pipe_1",
            "radius": 0.7,
            "height": 16,
            "axis": "x",
            "pos": [0, 6, 0],
            "color": C["heat_pipe"],
            "role": "heat pipe to radiator",
        },
        {
            "type": "panel",
            "name": "external_radiator",
            "size": [18, 0.6, 12],
            "pos": [16, 6, 0],
            "color": C["radiator"],
            "role": "external radiator",
        },
        {
            "type": "sphere",
            "name": "temp_sensor",
            "radius": 1.0,
            "pos": [4, 4, 5],
            "color": C["sensor"],
            "role": "board temperature sensor",
        },
    ]


_BUILDERS = {
    "lunar_thermal": _template_lunar_thermal,
    "hopper_lander": _template_hopper_lander,
    "propulsion": _template_propulsion,
    "electronics_bay": _template_electronics_bay,
}


def expand_template(
    template: str,
    scale: float = 1.0,
    params: dict | None = None,
) -> dict:
    """Expand a template id into a parts list + legend for explanations."""
    tid = (template or "").strip().lower().replace(" ", "_").replace("-", "_")
    # aliases
    aliases = {
        "thermal": "lunar_thermal",
        "lunar_hopper_thermal": "lunar_thermal",
        "hopper_thermal": "lunar_thermal",
        "heat": "lunar_thermal",
        "cooling": "lunar_thermal",
        "lander": "hopper_lander",
        "hopper": "hopper_lander",
        "vehicle": "hopper_lander",
        "engine": "propulsion",
        "rocket": "propulsion",
        "avionics": "electronics_bay",
        "electronics": "electronics_bay",
    }
    tid = aliases.get(tid, tid)
    builder = _BUILDERS.get(tid)
    if not builder:
        return {
            "ok": False,
            "error": f"unknown template {template!r}",
            "available": list(_BUILDERS.keys()),
        }

    try:
        s = float(scale)
    except (TypeError, ValueError):
        s = 1.0
    s = max(0.25, min(s, 4.0))

    raw_parts = builder(params or {})
    parts = [_scale_part(p, s) for p in raw_parts]
    legend = [
        {
            "name": p.get("name"),
            "role": p.get("role"),
            "color": p.get("color"),
            "type": p.get("type"),
        }
        for p in parts
    ]
    return {
        "ok": True,
        "template": tid,
        "scale": s,
        "part_count": len(parts),
        "parts": parts,
        "legend": legend,
        "color_key": {
            "blue": "tanks / fluids",
            "red": "radiators (heat out)",
            "gold": "heat pipes / transport",
            "cyan": "cold plates",
            "green": "avionics",
            "orange": "propulsion",
            "gray": "structure",
            "purple": "sensors",
        },
    }


def pick_template_for_prompt(text: str) -> str | None:
    """Heuristic template id from a natural-language request."""
    t = (text or "").lower()
    if any(w in t for w in ("thermal", "heat", "radiator", "cooling", "mli", "cryogen")):
        return "lunar_thermal"
    if any(w in t for w in ("propulsion", "engine", "nozzle", "thrust", "rocket")):
        return "propulsion"
    if any(w in t for w in ("avionics", "electronics", "pcb", "computer bay")):
        return "electronics_bay"
    if any(w in t for w in ("lander", "hopper", "vehicle", "legs", "whole craft")):
        return "hopper_lander"
    if "lunar" in t and "hopper" in t:
        return "hopper_lander"
    return None
