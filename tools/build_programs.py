"""Compile hub .py programs into Pybricks multi-file .mpy bundles.

Output goes to web-app/programs/<name>.mpy so the PWA can fetch them and
push them to each hub over BLE using the Pybricks remote-upload protocol
(WRITE_USER_PROGRAM_META + WRITE_USER_RAM + START_USER_PROGRAM).

Before compiling each entry point, the placeholder ``__NGTP_VERSION__`` in
every .py file inside hubs/ is replaced with the current git short SHA.
That string ends up in the compiled .mpy and is printed by the hub at boot
as ``VERSION <label> <sha>`` so the PWA can verify which build is running.

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
import os
import subprocess
import sys
import tempfile
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

VERSION_PLACEHOLDER = "__NGTP_VERSION__"


def detect_version(repo_root: Path) -> str:
    env = os.environ.get("NGTP_VERSION")
    if env:
        return env
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short=8", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return sha.decode("ascii").strip()
    except Exception:
        return "dev"


def stage_hubs_dir(repo_root: Path, dest: Path, version: str) -> None:
    """Copy hubs/ into dest and substitute the version placeholder."""
    src_dir = repo_root / "hubs"
    for src in src_dir.rglob("*.py"):
        rel = src.relative_to(src_dir)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        if VERSION_PLACEHOLDER in text:
            text = text.replace(VERSION_PLACEHOLDER, version)
        out.write_text(text, encoding="utf-8")


async def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "web-app" / "programs"
    out_dir.mkdir(parents=True, exist_ok=True)

    version = detect_version(repo_root)
    print(f"Building hub programs with VERSION={version}\n")

    manifest = {"version": version, "programs": {}}
    failed = []

    with tempfile.TemporaryDirectory(prefix="ngtp-hubs-") as td:
        staged = Path(td) / "hubs"
        stage_hubs_dir(repo_root, staged, version)

        for label, rel_path in ENTRIES.items():
            entry_name = Path(rel_path).name
            entry = staged / entry_name
            if not entry.exists():
                print(f"SKIP {label}: {rel_path} not found")
                failed.append(label)
                continue
            try:
                bundle = await compile_multi_file(str(entry), ABI_VERSION)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {label}: {exc}")
                failed.append(label)
                continue
            out = out_dir / f"{label}.mpy"
            out.write_bytes(bundle)
            manifest["programs"][label] = {
                "file": f"programs/{out.name}",
                "size": len(bundle),
                "version": version,
                "source": rel_path,
            }
            print(
                f"OK   {label}: {rel_path} -> {out.relative_to(repo_root)} "
                f"({len(bundle)} bytes, v={version})"
            )

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {out_dir / 'manifest.json'} ({len(manifest['programs'])} entries)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
