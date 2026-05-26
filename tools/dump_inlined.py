import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_programs import _strip_local_imports

repo = Path(__file__).resolve().parent.parent
hubs = repo / "hubs"
pieces = ['print("[boot] inlined entry alive")\n']
for dep in ["display_logic.py", "scoreboard_display.py"]:
    pieces.append(f"# --- inlined from {dep} ---\n")
    pieces.append(_strip_local_imports((hubs / dep).read_text(encoding="utf-8")))
    if not pieces[-1].endswith("\n"):
        pieces.append("\n")
pieces.append("# --- entry display_2.py ---\n")
pieces.append(_strip_local_imports((hubs / "display_2.py").read_text(encoding="utf-8")))
out = "".join(pieces)
target = repo / "_inlined_display_2.py"
target.write_text(out, encoding="utf-8")
print("written", target, "size=", len(out))
