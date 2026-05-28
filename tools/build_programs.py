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
import re
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


# Entry points that should be inlined into a single .py before compilation.
# Pybricks firmware 3.6 + pybricksdev 2.3 produce a multi-mpy bundle for
# anything that has local imports; the resulting bundle triggers a
# "RuntimeError: name too long" on the hub when the imported submodule's
# qstr window is parsed (see Display 2 logs from build v193c9a2c). Single
# .mpy files load cleanly, so we concatenate the dependency chain here.
# Order matters: the leaves come first so their definitions are in scope
# by the time the entry point's top-level code runs.
INLINE_CHAINS: dict[str, list[str]] = {
    "display_1.py": ["display_common.py"],
    "display_2.py": ["display_common.py"],
    "display_3.py": ["display_common.py"],
}

# Regex matches `from <name> import ...` for any of the modules we inline.
# Handles both `from display_common import x` and `from hubs.display_common
# import x` plus the `try/except ImportError` fallback by erasing the
# whole multi-line statement and any wrapping try/except block.
_INLINE_MODULE_NAMES = {"display_common"}


def _strip_local_imports(text: str) -> str:
    """Replace ``from <mod> import ...`` statements (incl. parenthesised
    multi-line forms) for any module we inline with a ``pass`` statement
    at the same indentation. Using ``pass`` keeps surrounding ``try`` /
    ``except ImportError`` blocks syntactically valid without us having
    to understand their structure."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        m = re.match(r"from\s+(?:hubs\.)?([A-Za-z_][\w]*)\s+import\b", stripped)
        if m and m.group(1) in _INLINE_MODULE_NAMES:
            indent = line[: len(line) - len(stripped)]
            # If this opens a parenthesised multi-line import, skip until
            # the closing ')'.
            if "(" in line and ")" not in line:
                i += 1
                while i < n and ")" not in lines[i]:
                    i += 1
                i += 1  # consume the ')'
            else:
                i += 1
            out.append(f"{indent}pass  # inlined import removed\n")
            continue
        out.append(line)
        i += 1
    return "".join(out)


def maybe_inline_entry(staged: Path, entry_name: str) -> Path:
    """If ``entry_name`` is in INLINE_CHAINS, create a sibling file with the
    deps concatenated and the local imports stripped, returning that path.
    Otherwise return the original staged path."""
    chain = INLINE_CHAINS.get(entry_name)
    if not chain:
        return staged / entry_name

    pieces: list[str] = []
    # Boot marker — printed before ANY import so that if the program runs
    # at all we will see this over BLE stdout. NOTE: display_common.py
    # constructs PrimeHub() at module load time precisely so this print
    # (and any subsequent ones) survive the BLE-stdout race; keep this
    # marker AFTER inlining so the hub is alive when it fires.
    pieces.append('print("[boot] inlined entry alive")\n')
    for dep in chain:
        dep_text = (staged / dep).read_text(encoding="utf-8")
        pieces.append(f"# --- inlined from {dep} ---\n")
        pieces.append(_strip_local_imports(dep_text))
        if not pieces[-1].endswith("\n"):
            pieces.append("\n")

    entry_text = (staged / entry_name).read_text(encoding="utf-8")
    pieces.append(f"# --- entry {entry_name} ---\n")
    pieces.append(_strip_local_imports(entry_text))

    inlined = staged / f"_inlined_{entry_name}"
    inlined.write_text("".join(pieces), encoding="utf-8")
    return inlined



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
            entry = maybe_inline_entry(staged, entry_name)
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

    # Substitute __NGTP_VERSION__ in web-app static files so every CI deploy
    # produces fresh asset URLs (?v=<sha>) and a unique SW cache name. This
    # is what makes the PWA actually pick up new code on installed devices,
    # bypassing the long GitHub Pages HTTP cache for app.js/style.css.
    web_root = repo_root / "web-app"
    # Patterns we re-stamp on every build. The first run replaces the
    # __NGTP_VERSION__ placeholder; later runs find the previous SHA stamp
    # at the same anchor and overwrite it. Without this, index.html and
    # sw.js would freeze on the first deploy's SHA and GitHub Pages would
    # keep serving the cached app.js?v=<old-sha>.
    stamp_patterns = [
        # ?v=<sha> on app.js / style.css references
        (re.compile(r"(\?v=)(?:__NGTP_VERSION__|[0-9a-f]{7,40})"), r"\g<1>" + version),
        # <span id="pwa-version">SHA</span>
        (
            re.compile(r'(id="pwa-version">)(?:__NGTP_VERSION__|[0-9a-f]{7,40})(<)'),
            r"\g<1>" + version + r"\g<2>",
        ),
        # SW cache name "ngtp-<sha>"
        (
            re.compile(r'("ngtp-)(?:__NGTP_VERSION__|[0-9a-f]{7,40})(")'),
            r"\g<1>" + version + r"\g<2>",
        ),
    ]
    for rel in ("index.html", "sw.js"):
        path = web_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        new_text = text
        for pat, repl in stamp_patterns:
            new_text = pat.sub(repl, new_text)
        # Also handle any straggler placeholder occurrences not covered above.
        new_text = new_text.replace(VERSION_PLACEHOLDER, version)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"Stamped {rel} with v={version}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
