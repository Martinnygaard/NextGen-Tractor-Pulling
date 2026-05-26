"""Compile a minimal hello-world .mpy bundle and write it to the PWA programs dir.

Use this to verify whether the hub's mpy loader works at all on the
current firmware. Replaces web-app/programs/display2.mpy temporarily.
"""
import asyncio
import shutil
import tempfile
from pathlib import Path

from pybricksdev.compile import compile_multi_file

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web-app" / "programs" / "display2.mpy"

SOURCE = 'print("hello from hub")\n'

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    entry = td / "hello.py"
    entry.write_text(SOURCE, encoding="utf-8")
    blob = asyncio.run(compile_multi_file(str(entry), 6))
    print("blob size:", len(blob))
    print("first 64 hex:", blob[:64].hex(" "))
    # Backup current
    if OUT.exists():
        shutil.copy2(OUT, OUT.with_suffix(".mpy.bak"))
    OUT.write_bytes(blob)
    print(f"wrote {OUT} ({len(blob)} bytes)")
