#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_index.py — compile examples/<slug>/meta.yaml + _extracted/*.cam.json
                  into a single examples.json at the repo root.

The site (techcnc.ca /machining-examples) fetches that file via jsDelivr:

    https://cdn.jsdelivr.net/gh/TechCNC/Examples@main/examples.json

Usage:
    python _scripts/build_index.py              # default
    python _scripts/build_index.py --strict     # error on missing fields
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "PyYAML is required: pip install pyyaml\n"
        "(used to parse meta.yaml files in examples/<slug>/)\n"
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
EXTRACTED_DIR = REPO_ROOT / "_extracted"
OUTPUT_FILE = REPO_ROOT / "examples.json"
README_FILE = REPO_ROOT / "README.md"

# jsDelivr CDN base for serving static assets (previews) from the repo.
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/TechCNC/Examples@main"

README_MARKER_START = "<!-- DOWNLOADS_START -->"
README_MARKER_END = "<!-- DOWNLOADS_END -->"


# ---------- helpers -----------------------------------------------------------

def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cam_json(source_document: str) -> dict | None:
    if not source_document:
        return None
    candidate = EXTRACTED_DIR / f"{source_document}.cam.json"
    if not candidate.exists():
        # try simple sanitization (Fusion writes some chars escaped)
        safe = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in source_document).strip()
        candidate = EXTRACTED_DIR / f"{safe}.cam.json"
    if not candidate.exists():
        # last try — fuzzy match for Fusion's " vN" version suffix
        matches = sorted(EXTRACTED_DIR.glob(f"{source_document}*.cam.json"))
        if matches:
            candidate = matches[-1]
        else:
            return None
    with candidate.open("r", encoding="utf-8") as f:
        return json.load(f)


def merge_cam(cams: list[dict]) -> dict | None:
    """Combine several extracted CAM dumps into one — for multi-file examples."""
    cams = [c for c in cams if c]
    if not cams:
        return None
    if len(cams) == 1:
        return cams[0]
    merged = {
        "schemaVersion": cams[0].get("schemaVersion", 1),
        "documentName": " + ".join(c.get("documentName", "?") for c in cams),
        "extractedAt": cams[0].get("extractedAt"),
        "setups": [],
        "uniqueTools": [],
    }
    seen_tools = set()
    total_setups = 0
    total_ops = 0
    total_time = 0.0
    for c in cams:
        for s in c.get("setups", []):
            merged["setups"].append(s)
            total_setups += 1
            total_ops += s.get("totalOperations", 0)
            ct = s.get("totalCycleTimeMin")
            if ct:
                total_time += ct
        for t in c.get("uniqueTools", []):
            key = (t.get("number"), t.get("description"))
            if key not in seen_tools:
                seen_tools.add(key)
                merged["uniqueTools"].append(t)
    merged["stats"] = {
        "totalSetups": total_setups,
        "totalOperations": total_ops,
        "totalCycleTimeMin": round(total_time, 2) if total_time else None,
        "uniqueToolCount": len(merged["uniqueTools"]),
    }
    return merged


def resolve_source_documents(meta: dict) -> list[str]:
    """Return a list — supports new `source_documents` and legacy `source_document`."""
    docs = meta.get("source_documents")
    if isinstance(docs, list) and docs:
        return [str(d) for d in docs if d]
    single = meta.get("source_document")
    return [str(single)] if single else []


def resolve_drive_files(meta: dict) -> list[dict]:
    """Return [{label, file_id, url}, ...] for the modal download buttons."""
    files = meta.get("drive_files")
    if isinstance(files, list) and files:
        out = []
        for f in files:
            if not isinstance(f, dict):
                continue
            url = f.get("url")
            if not url:
                continue
            out.append({
                "label": f.get("label") or "Download",
                "fileId": f.get("file_id"),
                "url": url,
            })
        return out
    # Legacy single drive entry
    legacy = meta.get("drive") or {}
    url = legacy.get("url")
    if url:
        return [{
            "label": "Download .f3d / .f3z",
            "fileId": legacy.get("file_id"),
            "url": url,
        }]
    return []


def summarize_cam(cam: dict | None) -> dict:
    """Compact stats block for the card view."""
    if not cam:
        return {
            "totalSetups": 0,
            "totalOperations": 0,
            "totalCycleTimeMin": None,
            "uniqueToolCount": 0,
            "strategies": [],
            "toolTypes": [],
        }

    stats = cam.get("stats") or {}
    strategies: list[str] = []
    tool_types: set[str] = set()
    for s in cam.get("setups", []):
        for op in s.get("operations", []):
            strat = op.get("strategy")
            if strat and strat not in strategies:
                strategies.append(strat)
            tool = op.get("tool") or {}
            t_type = tool.get("type")
            if t_type:
                tool_types.add(t_type)

    return {
        "totalSetups": stats.get("totalSetups") or len(cam.get("setups", [])),
        "totalOperations": stats.get("totalOperations") or 0,
        "totalCycleTimeMin": stats.get("totalCycleTimeMin"),
        "uniqueToolCount": stats.get("uniqueToolCount") or len(cam.get("uniqueTools", [])),
        "strategies": strategies,
        "toolTypes": sorted(tool_types),
    }


def default_short_summary(meta: dict, summary: dict) -> str:
    parts: list[str] = []
    if summary["totalOperations"]:
        parts.append(f"{summary['totalOperations']} ops")
    if summary["totalCycleTimeMin"]:
        ct = summary["totalCycleTimeMin"]
        if ct >= 60:
            parts.append(f"~{ct/60:.1f} h")
        else:
            parts.append(f"~{ct:.0f} min")
    mat = meta.get("material")
    if mat:
        parts.append(mat)
    return ", ".join(parts) if parts else ""


def asset_url(slug: str, filename: str) -> str:
    # jsDelivr-friendly URL for static assets bundled with the repo.
    return f"{JSDELIVR_BASE}/examples/{slug}/{filename}"


def render_downloads_table(examples: list[dict]) -> str:
    rows = ["| Project | Material | Time | Download |",
            "|---------|----------|------|----------|"]
    for ex in examples:
        title = ex.get("title") or ex["slug"]
        material = ex.get("material") or "—"
        ct = (ex.get("summary") or {}).get("totalCycleTimeMin")
        if ct:
            time_label = f"~{ct/60:.1f} h" if ct >= 60 else f"~{int(round(ct))} min"
        else:
            time_label = "—"
        files = ex.get("driveFiles") or []
        if files:
            link = " · ".join(f"[⬇ {f.get('label') or 'Download'}]({f['url']})" for f in files)
        else:
            link = "_pending_"
        rows.append(f"| **{title}** | {material} | {time_label} | {link} |")
    return "\n".join(rows)


def update_readme_downloads(examples: list[dict]) -> bool:
    """Rewrites the block between README_MARKER_START / _END with a fresh table.
    Returns True if the README was updated, False if markers are missing.
    """
    if not README_FILE.exists():
        return False
    text = README_FILE.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(README_MARKER_START) + r".*?" + re.escape(README_MARKER_END),
        re.DOTALL,
    )
    if not pattern.search(text):
        return False
    block = (
        f"{README_MARKER_START}\n"
        "<!-- Auto-generated by _scripts/build_index.py. Edit meta.yaml, not this. -->\n\n"
        + render_downloads_table(examples)
        + f"\n\n{README_MARKER_END}"
    )
    README_FILE.write_text(pattern.sub(block, text), encoding="utf-8")
    return True


# ---------- main --------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any example lacks drive.url or cam.json")
    args = ap.parse_args()

    if not EXAMPLES_DIR.exists():
        sys.stderr.write(f"No examples/ folder at {EXAMPLES_DIR}\n")
        return 1

    items = []
    warnings: list[str] = []

    for slug_dir in sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir()):
        slug = slug_dir.name
        meta_path = slug_dir / "meta.yaml"
        if not meta_path.exists():
            warnings.append(f"[skip] {slug}: no meta.yaml")
            continue

        meta = load_yaml(meta_path)

        # Load CAM data — merge multiple if source_documents is a list.
        source_docs = resolve_source_documents(meta)
        cams = [load_cam_json(d) for d in source_docs]
        missing = [d for d, c in zip(source_docs, cams) if c is None]
        for d in missing:
            warnings.append(f"[warn] {slug}: cam.json not found for source_document='{d}'")
        cam = merge_cam([c for c in cams if c])

        summary = summarize_cam(cam)
        short = meta.get("short_summary") or default_short_summary(meta, summary)

        drive_files = resolve_drive_files(meta)
        if not drive_files:
            warnings.append(f"[warn] {slug}: no drive URL(s)")

        item = {
            "slug": meta.get("slug") or slug,
            "title": meta.get("title") or slug,
            "material": meta.get("material"),
            "machine": meta.get("machine"),
            "difficulty": meta.get("difficulty"),
            "tags": meta.get("tags") or [],
            "description": (meta.get("description") or "").strip(),
            "shortSummary": short,
            "preview": asset_url(slug, meta.get("preview") or "preview.jpg"),
            # `driveFiles` is the new canonical multi-file array. `drive`
            # stays for back-compat with older clients reading examples.json.
            "driveFiles": drive_files,
            "drive": {
                "fileId": (drive_files[0] if drive_files else {}).get("fileId"),
                "url":    (drive_files[0] if drive_files else {}).get("url"),
            },
            "summary": summary,
            # Full per-op data — included so the modal can show feeds/speeds.
            # Kept as-is from cam.json; clients can ignore if they only need cards.
            "cam": cam,
        }
        items.append(item)

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "github.com/TechCNC/Examples",
        "count": len(items),
        "examples": items,
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {OUTPUT_FILE.relative_to(REPO_ROOT)}: {len(items)} examples")

    if update_readme_downloads(items):
        print(f"Updated {README_FILE.relative_to(REPO_ROOT)} downloads table")
    else:
        print(f"Skipped README update (no {README_MARKER_START} markers)")

    for w in warnings:
        print(w)

    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
