#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bundle_preview.py — produce a self-contained preview of the Machining Examples
page that runs from file:// (double-click in Explorer, no web server).

Reads:
    examples.json
    _site/machining-examples.html

Writes (default):
    H:\\My Drive\\TECHCNC\\Everething about WebSite\\Examples\\preview.html

The output file is the production HTML with `examples.json` injected as a
`window.TC_MEX_DATA` constant (so no fetch is needed) and each example's
preview URL rewritten to a local filename in the same folder — picks up the
original .jpg files that already live next to it.

Re-run whenever you edit a meta.yaml or extract new CAM data:

    python _scripts/build_index.py        # refresh examples.json
    python _scripts/bundle_preview.py     # refresh preview.html
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "examples.json"
HTML_PATH = REPO_ROOT / "_site" / "machining-examples.html"

DEFAULT_OUTPUT = Path(r"H:\My Drive\TECHCNC\Everething about WebSite\Examples\preview.html")


def transform(data: dict) -> dict:
    """Rewrite each example's preview URL to a local filename.

    Pairs example.cam.documentName with `<documentName>.jpg` — that matches
    the original Fusion-export jpgs that already sit next to preview.html.
    """
    for ex in data.get("examples", []):
        cam = ex.get("cam") or {}
        doc = cam.get("documentName") or ex.get("slug") or ""
        if doc:
            ex["preview"] = urllib.parse.quote(doc + ".jpg")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                    help="Output HTML path (default: H:\\...\\Everething about WebSite\\Examples\\preview.html)")
    args = ap.parse_args()

    if not DATA_PATH.exists():
        sys.stderr.write(f"Missing {DATA_PATH}. Run build_index.py first.\n")
        return 1
    if not HTML_PATH.exists():
        sys.stderr.write(f"Missing {HTML_PATH}.\n")
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    data = transform(data)
    html = HTML_PATH.read_text(encoding="utf-8")

    inject = (
        "<!-- bundle_preview.py: inlined data, overrides remote fetch -->\n"
        "<script>\n"
        "window.TC_MEX_DATA = "
        + json.dumps(data, ensure_ascii=False)
        + ";\n</script>\n"
    )
    bundled = inject + html

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(bundled, encoding="utf-8")

    size_kb = args.output.stat().st_size / 1024
    print(f"Wrote {args.output}")
    print(f"  size:     {size_kb:.1f} KB")
    print(f"  examples: {len(data.get('examples', []))}")
    print()
    print("Open it by double-clicking the file — works from any browser without a server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
