"""Compile hub .py programs into Pybricks multi-file .mpy bundles.

Output goes to web-app/programs/<name>.mpy so the PWA can fetch them and
push them to each hub over BLE using the Pybricks remote-upload protocol
(WRITE_USER_PROGRAM_META + WRITE_USER_RAM + START_USER_PROGRAM).

The mapping between hub label (used in the PWA) and entry-point file:

    master    -> hubs/master_broadcaster.py
    sled      -> hubs/sled.py
    display1  -> hubs/display_1.py
    display2  -> hubs/display_2.py
    display3  -> hubs/display_3.py

Run locally:
    python -m pip install pybricksdev
    python tools/build_programs.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from pybricksdev.compile import compile_multi_file

# Pybricks 3.x firmware uses MicroPython mpy ABI v6.
ABI_VERSION = 6

ENTRIES = {
    "master": "hubs/master_broadcaster.py",
    "sled": "hubs/sled.py",
    "display1": "hubs/display_1.py",
    "display2": "hubs/display_2.py",
    "display3": "hubs/display_3.py",
}


async def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "web-app" / "programs"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {}
    failed = []

    for label, rel_path in ENTRIES.items():
        src = repo_root / rel_path
        if not src.exists():
            print(f"SKIP {label}: {rel_path} not found")
            failed.append(label)
            continue
        try:
            bundle = await compile_multi_file(str(src), ABI_VERSION)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {label}: {exc}")
            failed.append(label)
            continue
        out = out_dir / f"{label}.mpy"
        out.write_bytes(bundle)
        manifest[label] = {
            "file": f"programs/{out.name}",
            "size": len(bundle),
            "source": rel_path,
        }
        print(f"OK   {label}: {rel_path} -> {out.relative_to(repo_root)} ({len(bundle)} bytes)")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out_dir / 'manifest.json'}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
