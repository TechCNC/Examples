# TechCNC / Examples

Public catalog of real Fusion 360 machining projects from the TechCNC shop —
each example bundles the source `.f3d` / `.f3z` file (hosted on Google Drive),
a rendered preview, and full extracted CAM data (every operation, every tool,
every feed and speed).

The catalog powers the **Machining Examples** page on
[techcnc.ca](https://techcnc.ca) via a single JSON file served from jsDelivr:

```
https://cdn.jsdelivr.net/gh/TechCNC/Examples@main/examples.json
```

## Repository layout

```
.
├── examples.json              ← compiled index (consumed by techcnc.ca)
├── examples/
│   └── <slug>/
│       ├── meta.yaml          ← human-edited: title, material, drive URL, description
│       └── preview.jpg        ← card / hero image
├── _extracted/
│   └── <DocName>.cam.json     ← raw CAM dump from Fusion 360 (one per project)
├── _sources/                  ← .f3z / .f3d originals (gitignored, ~120 MB)
│                                Auto-synced to G: Drive; copied to the public
│                                TechCNC Drive folder via copy_to_drive.ps1.
├── _scripts/
│   ├── extract_cam_data.py    ← Fusion 360 script (run via Scripts and Add-Ins)
│   ├── build_index.py         ← compiles examples/ + _extracted/ → examples.json
│   └── copy_to_drive.ps1      ← syncs _sources/ → H:\Public CNC Data\Examples\
└── _site/
    └── machining-examples.html ← paste-into-Elementor block (Custom HTML widget)
```

## Adding a new example

1. **Drop the source file into `_sources/`.** Use the original Fusion 360
   filename — it becomes the `source_document` key (without extension) that
   ties everything together. The file syncs to G: Drive automatically and is
   gitignored, so it never reaches GitHub.

2. **Extract CAM data.**
   - In Fusion 360: open the file from `_sources/`, then
     `Utilities ▸ Add-Ins ▸ Scripts and Add-Ins ▸ Scripts ▸ +`,
     select `_scripts/extract_cam_data.py`, click *Run*.
   - The script writes `_extracted/<DocName>.cam.json` and shows a confirmation
     dialog with the operation / cycle-time counts.

3. **Create the example folder.**
   - Pick a kebab-case slug (e.g. `vacuum-plate-grid`).
   - `mkdir examples/<slug>` and drop a `preview.jpg` (4:3 ratio works best).
   - Copy `examples/<existing>/meta.yaml` to the new folder and edit:
     - `slug` — match the folder name.
     - `title` — display title.
     - `source_document` — **exact** Fusion 360 document name (no extension).
     - `material`, `machine`, `difficulty`, `tags`, `description`.

4. **Publish the source file to Drive.**
   - Run `_scripts/copy_to_drive.ps1` — copies new/updated files from
     `_sources/` to `H:\My Drive\TECHCNC\Public CNC Data\Examples\`.
   - In `drive.google.com`, right-click the file → **Share → Anyone with the
     link → Viewer** → copy URL.
   - Paste URL into `examples/<slug>/meta.yaml` under `drive.url`.

5. **Rebuild the index.**
   ```bash
   python _scripts/build_index.py
   ```
   This regenerates `examples.json`. Warnings are printed for any example
   missing CAM data or a Drive URL; they're allowed but show up greyed-out
   on the site.

6. **Commit and push.**
   ```bash
   git add examples/<slug>/ _extracted/<DocName>.cam.json examples.json
   git commit -m "Add <slug> example"
   git push
   ```

7. **Refresh the site cache.** jsDelivr caches `examples.json` for ~12 hours.
   To force-refresh immediately, visit:
   ```
   https://purge.jsdelivr.net/gh/TechCNC/Examples@main/examples.json
   ```

## Editing or removing an example

- **Edit:** change `examples/<slug>/meta.yaml`, re-run `build_index.py`, commit.
- **Remove:** delete the `examples/<slug>/` folder and its
  `_extracted/<DocName>.cam.json`, re-run `build_index.py`, commit.

## Schema

Each entry in `examples.json` has:

| Field          | Type    | Description                                              |
|----------------|---------|----------------------------------------------------------|
| `slug`         | string  | Stable URL-safe identifier.                              |
| `title`        | string  | Display title.                                           |
| `material`     | string  | e.g. `6061 aluminum`.                                    |
| `machine`      | string  | e.g. `AP4060`.                                           |
| `difficulty`   | string  | `easy` \| `medium` \| `hard`.                            |
| `tags`         | array   | Free-text tags; site uses top-8 as filter chips.         |
| `description`  | string  | Multi-line markdown-flavored text.                       |
| `shortSummary` | string  | One-line subtitle (auto-built if blank).                 |
| `preview`      | string  | jsDelivr URL to `preview.jpg`.                           |
| `drive.url`    | string  | Google Drive "Anyone with link" download URL.            |
| `drive.fileId` | string  | Drive file id (optional, for programmatic use).          |
| `summary`      | object  | Pre-aggregated stats (ops, time, tools, strategies).     |
| `cam`          | object  | Full extracted CAM data (all setups, operations, tools). |

## License

[MIT](LICENSE) — code, scripts, and JSON data.
Preview images and CAM data are © TechCNC and shared for educational use.
