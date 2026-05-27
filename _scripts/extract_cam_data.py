# -*- coding: utf-8 -*-
"""
TechCNC — Fusion 360 CAM data extractor.

Iterates all CAM setups in the active document and writes a JSON file to
`_extracted/<documentName>.cam.json` (next to the script).

Workflow:
  1. Open .f3d / .f3z in Fusion 360 (Manufacture workspace must be available).
  2. Utilities -> Add-Ins -> Scripts and Add-Ins -> Scripts -> + -> select this file.
  3. Run. A messagebox shows the output path on success.

The script tolerates missing parameters / strategies and never raises in the
operator's face: anything it can't read becomes `null` in the JSON.
"""

import os
import json
import time
import traceback

import adsk.core
import adsk.fusion
import adsk.cam


# ---------- output location ----------------------------------------------------

# Folder where extracted JSONs land. Sits next to this script under
# G:\My Drive\Public_Tech_CNC_Data\Examples\_scripts\, so result goes into
# G:\My Drive\Public_Tech_CNC_Data\Examples\_extracted\.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "_extracted"))


# ---------- safe parameter helpers --------------------------------------------

def _safe_attr(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _get_param(params, name):
    """Return the CAMParameter for `name` or None. Never raises."""
    if params is None:
        return None
    try:
        p = params.itemByName(name)
    except Exception:
        return None
    return p


def _read_value(params, name):
    """
    Read a CAM parameter and return a dict like:
        {"value": <float|int|bool|str|None>, "expression": "<str>"}
    or None if the parameter does not exist on this op/tool.

    `.value` is in Fusion-internal units (length=cm, time=s, feed=cm/s, etc.).
    `.expression` is the user-facing string with units ("6 mm", "1200 mm/min").
    Downstream code should prefer .expression for display and .value for math.
    """
    p = _get_param(params, name)
    if p is None:
        return None
    out = {"value": None, "expression": None}
    # .value lives on the parameter's typed value object; flavor varies.
    try:
        v = p.value
        # FloatParameterValue/IntegerParameterValue/BooleanParameterValue all
        # expose .value. If we hit a complex type, fall through.
        try:
            out["value"] = v.value
        except Exception:
            out["value"] = v
    except Exception:
        pass
    try:
        out["expression"] = p.expression
    except Exception:
        pass
    return out


def _num(reading, scale=1.0, ndigits=4):
    """Pull the numeric .value from a _read_value() result, scaled. None-safe."""
    if not reading or reading.get("value") is None:
        return None
    try:
        return round(float(reading["value"]) * scale, ndigits)
    except (TypeError, ValueError):
        return None


# Fusion 360 internal -> display unit factors.
# Length: cm -> mm  =>  x10
# Feed:   cm/s -> mm/min  =>  x600
# Spindle: stored as RPM already in CAM context (verified empirically); no scale.
CM_TO_MM = 10.0
CMS_TO_MM_MIN = 600.0


# ---------- tool extraction ----------------------------------------------------

def _tool_to_dict(tool):
    if tool is None:
        return None
    tp = _safe_attr(tool, "parameters")
    desc = _read_value(tp, "tool_description")
    return {
        "number": _num(_read_value(tp, "tool_number"), ndigits=0),
        "description": (desc or {}).get("value") or (desc or {}).get("expression"),
        "type": (_read_value(tp, "tool_type") or {}).get("value"),
        "diameter_mm": _num(_read_value(tp, "tool_diameter"), CM_TO_MM),
        "corner_radius_mm": _num(_read_value(tp, "tool_cornerRadius"), CM_TO_MM),
        "flute_length_mm": _num(_read_value(tp, "tool_fluteLength"), CM_TO_MM),
        "shoulder_length_mm": _num(_read_value(tp, "tool_shoulderLength"), CM_TO_MM),
        "overall_length_mm": _num(_read_value(tp, "tool_bodyLength"), CM_TO_MM),
        "flutes": _num(_read_value(tp, "tool_numberOfFlutes"), ndigits=0),
        "material": (_read_value(tp, "tool_material") or {}).get("value"),
        "coolant": (_read_value(tp, "tool_coolant") or {}).get("value"),
    }


# ---------- operation extraction ----------------------------------------------

def _op_to_dict(op):
    """Extract a CAMOperation. Returns dict; never raises."""
    params = _safe_attr(op, "parameters")
    tool = _safe_attr(op, "tool")

    # cuttingTime is on Operation directly (seconds). Not always present
    # — depends on whether toolpaths have been generated.
    cutting_time_s = _safe_attr(op, "cuttingTime")
    try:
        cutting_time_min = round(float(cutting_time_s) / 60.0, 2) if cutting_time_s else None
    except (TypeError, ValueError):
        cutting_time_min = None

    return {
        "name": _safe_attr(op, "name"),
        "strategy": _safe_attr(op, "strategy"),
        "operationId": _safe_attr(op, "operationId"),
        "isSuppressed": bool(_safe_attr(op, "isSuppressed", False)),
        "hasToolpath": bool(_safe_attr(op, "hasToolpath", False)),
        "tool": _tool_to_dict(tool),
        "feeds_speeds": {
            "spindle_rpm": _num(_read_value(params, "tool_spindleSpeed"), ndigits=0),
            "surface_speed_m_min": _num(_read_value(params, "tool_surfaceSpeed"), CMS_TO_MM_MIN / 1000.0, 1),
            "feed_cutting_mm_min": _num(_read_value(params, "tool_feedCutting"), CMS_TO_MM_MIN),
            "feed_lead_in_mm_min": _num(_read_value(params, "tool_feedLeadIn"), CMS_TO_MM_MIN),
            "feed_lead_out_mm_min": _num(_read_value(params, "tool_feedLeadOut"), CMS_TO_MM_MIN),
            "feed_plunge_mm_min": _num(_read_value(params, "tool_feedPlunge"), CMS_TO_MM_MIN),
            "feed_ramp_mm_min": _num(_read_value(params, "tool_feedRamp"), CMS_TO_MM_MIN),
            "feed_entry_mm_min": _num(_read_value(params, "tool_feedEntry"), CMS_TO_MM_MIN),
            "feed_exit_mm_min": _num(_read_value(params, "tool_feedExit"), CMS_TO_MM_MIN),
            "feed_per_tooth_mm": _num(_read_value(params, "tool_feedPerTooth"), CM_TO_MM, 5),
            "chip_load_mm": _num(_read_value(params, "tool_chipLoad"), CM_TO_MM, 5),
        },
        "geometry": {
            "stepdown_mm": _num(_read_value(params, "maximumStepdown"), CM_TO_MM),
            "stepover_mm": _num(_read_value(params, "maximumStepover"), CM_TO_MM),
            "stock_to_leave_mm": _num(_read_value(params, "stockToLeave"), CM_TO_MM),
            "axial_stock_to_leave_mm": _num(_read_value(params, "axialStockToLeave"), CM_TO_MM),
            "radial_stock_to_leave_mm": _num(_read_value(params, "radialStockToLeave"), CM_TO_MM),
            "tolerance_mm": _num(_read_value(params, "tolerance"), CM_TO_MM, 5),
        },
        "cycle_time_min": cutting_time_min,
    }


# ---------- setup extraction --------------------------------------------------

def _setup_to_dict(setup):
    ops = []
    try:
        all_ops = setup.allOperations
    except Exception:
        all_ops = []

    for op in all_ops:
        try:
            ops.append(_op_to_dict(op))
        except Exception as e:
            ops.append({
                "name": _safe_attr(op, "name", "<unreadable>"),
                "error": "extraction failed: {}".format(e),
            })

    total_time = 0.0
    for o in ops:
        ct = o.get("cycle_time_min")
        if ct:
            total_time += float(ct)

    # Stock box (mm) — Fusion stores setup.stock as a BRep box internally
    stock = None
    try:
        s = setup.stock
        if s and hasattr(s, "boundingBox") and s.boundingBox:
            bb = s.boundingBox
            stock = {
                "x_mm": round((bb.maxPoint.x - bb.minPoint.x) * CM_TO_MM, 2),
                "y_mm": round((bb.maxPoint.y - bb.minPoint.y) * CM_TO_MM, 2),
                "z_mm": round((bb.maxPoint.z - bb.minPoint.z) * CM_TO_MM, 2),
            }
    except Exception:
        stock = None

    return {
        "setupName": _safe_attr(setup, "name"),
        "operationType": _safe_attr(setup, "operationType"),
        "isSuppressed": bool(_safe_attr(setup, "isSuppressed", False)),
        "stock": stock,
        "operations": ops,
        "totalOperations": len(ops),
        "totalCycleTimeMin": round(total_time, 2) if total_time else None,
    }


# ---------- entry point --------------------------------------------------------

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument

        if not doc:
            ui.messageBox("No active document.")
            return

        product = doc.products.itemByProductType("CAMProductType")
        if not product:
            ui.messageBox("Active document has no CAM (Manufacture) workspace data.")
            return
        cam = adsk.cam.CAM.cast(product)

        setups_data = []
        for s in cam.setups:
            setups_data.append(_setup_to_dict(s))

        # Aggregate unique tools across all setups (deduped by number+description)
        unique = {}
        for s in setups_data:
            for op in s["operations"]:
                t = op.get("tool") or {}
                key = (t.get("number"), t.get("description"))
                if t and any(key) and key not in unique:
                    unique[key] = t
        unique_tools = list(unique.values())

        total_ops = sum(s["totalOperations"] for s in setups_data)
        total_time = sum((s["totalCycleTimeMin"] or 0) for s in setups_data)

        output = {
            "schemaVersion": 1,
            "documentName": doc.name,
            "extractedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "setups": setups_data,
            "uniqueTools": unique_tools,
            "stats": {
                "totalSetups": len(setups_data),
                "totalOperations": total_ops,
                "totalCycleTimeMin": round(total_time, 2) if total_time else None,
                "uniqueToolCount": len(unique_tools),
            },
        }

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe_name = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in doc.name).strip()
        out_path = os.path.join(OUTPUT_DIR, safe_name + ".cam.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        ui.messageBox(
            "CAM data extracted.\n\n"
            "Setups: {0}\nOperations: {1}\nCycle time: {2} min\n\n"
            "Saved to:\n{3}".format(
                len(setups_data),
                total_ops,
                round(total_time, 2) if total_time else "?",
                out_path,
            )
        )
    except Exception:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
        else:
            raise
