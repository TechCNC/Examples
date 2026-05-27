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

# jsDelivr CDN base for serving static assets (previews) from the repo.
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/TechCNC/Examples@main"


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
        return None
    with candidate.open("r", encoding="utf-8") as f:
        return json.load(f)


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
        cam = load_cam_json(meta.get("source_document"))
        if cam is None and meta.get("source_document"):
            warnings.append(f"[warn] {slug}: cam.json not found for "
                            f"source_document='{meta['source_document']}'")

        summary = summarize_cam(cam)
        short = meta.get("short_summary") or default_short_summary(meta, summary)

        drive = meta.get("drive") or {}
        if not drive.get("url"):
            warnings.append(f"[warn] {slug}: drive.url is empty")

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
            "drive": {
                "fileId": drive.get("file_id") or None,
                "url": drive.get("url") or None,
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
    for w in warnings:
        print(w)

    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
