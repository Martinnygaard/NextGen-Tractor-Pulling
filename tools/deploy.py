"""Compile, upload and start Pybricks programs on one or more hubs over BLE.

Uses the same pybricksdev API as server/bridge_client.py:
    find_device(name) -> PybricksHubBLE -> connect() -> run(script)

Configuration
-------------
Hub BLE names live in ``tools/hubs.json``. On first run this script writes a
template you can edit:

    {
        "master":   "PullMaster",
        "display1": "PullDisplay1",
        "display2": "PullDisplay2",
        "display3": "PullDisplay3",
        "sled":     "PullSled"
    }

Usage
-----
    python tools/deploy.py                       # deploy all hubs in hubs.json
    python tools/deploy.py display1              # deploy a single hub
    python tools/deploy.py display1 display2     # deploy specific hubs
    python tools/deploy.py --watch display1      # stay connected and stream stdout

Notes
-----
* The script uploads the source ``.py`` (pybricksdev handles compilation).
* Without ``--watch`` the script starts the program and disconnects; Pybricks
  firmware keeps the program running after BLE drops.
* With ``--watch`` it streams hub stdout until you press Ctrl+C. The program
  is stopped on disconnect in that mode (pybricksdev's normal behaviour).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HUBS_CFG = REPO / "tools" / "hubs.json"

# label -> script path (relative to repo root)
SCRIPTS: dict[str, Path] = {
    "master":      REPO / "hubs" / "master_broadcaster.py",
    "scoremaster": REPO / "hubs" / "score_master.py",
    "display1":    REPO / "hubs" / "display_1.py",
    "display2":    REPO / "hubs" / "display_2.py",
    "display3":    REPO / "hubs" / "display_3.py",
    "sled":        REPO / "hubs" / "sled.py",
}

DEFAULT_NAMES: dict[str, str] = {
    "master":      "Puller Master",
    "scoremaster": "Puller Master",
    "display1":    "Puller Score 1",
    "display2":    "Puller Score 2",
    "display3":    "Puller Score 3",
    "sled":        "Puller Sled",
}

SCAN_TIMEOUT = 15.0
START_GRACE_SEC = 2.0  # let the program boot before we disconnect


def load_config() -> dict[str, str]:
    if HUBS_CFG.exists():
        return json.loads(HUBS_CFG.read_text(encoding="utf-8"))
    HUBS_CFG.write_text(json.dumps(DEFAULT_NAMES, indent=2), encoding="utf-8")
    print(f"[deploy] wrote template {HUBS_CFG}")
    print("[deploy] edit it with your hub BLE names and re-run.")
    sys.exit(2)


async def deploy_one(label: str, name: str, script: Path, watch: bool) -> None:
    from pybricksdev.ble import find_device
    from pybricksdev.connections.pybricks import PybricksHubBLE

    print(f"[{label}] scanning for '{name}' (timeout {SCAN_TIMEOUT:.0f}s)...")
    device = await find_device(name, timeout=SCAN_TIMEOUT)
    hub = PybricksHubBLE(device)
    print(f"[{label}] connecting...")
    await hub.connect()
    try:
        if watch:
            print(f"[{label}] running {script.name} (streaming stdout, Ctrl+C to stop)...")
            await hub.run(str(script), wait=True, print_output=True, line_handler=False)
            print(f"[{label}] program ended")
        else:
            print(f"[{label}] uploading {script.name} and starting...")
            await hub.run(str(script), wait=False, print_output=False, line_handler=False)
            await asyncio.sleep(START_GRACE_SEC)
            print(f"[{label}] OK - program started, disconnecting")
    finally:
        try:
            await hub.disconnect()
        except Exception:
            pass


async def deploy_all(labels: list[str], cfg: dict[str, str], watch: bool) -> int:
    failed: list[str] = []
    for label in labels:
        if label not in SCRIPTS:
            print(f"[{label}] unknown label (known: {', '.join(SCRIPTS)})")
            failed.append(label)
            continue
        if label not in cfg:
            print(f"[{label}] missing entry in {HUBS_CFG.name}")
            failed.append(label)
            continue
        if not SCRIPTS[label].exists():
            print(f"[{label}] script not found: {SCRIPTS[label]}")
            failed.append(label)
            continue
        try:
            await deploy_one(label, cfg[label], SCRIPTS[label], watch)
        except KeyboardInterrupt:
            print(f"\n[{label}] interrupted")
            return 130
        except Exception as exc:
            print(f"[{label}] FAILED: {exc!r}")
            failed.append(label)

    if failed:
        print(f"\n[deploy] failed: {', '.join(failed)}")
        return 1
    print("\n[deploy] all hubs deployed successfully")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Pybricks programs to hubs.")
    parser.add_argument(
        "labels",
        nargs="*",
        help="Hub labels to deploy (default: all in hubs.json).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Stream stdout from the hub instead of disconnecting after start.",
    )
    args = parser.parse_args()

    cfg = load_config()
    labels = args.labels if args.labels else list(cfg.keys())

    if args.watch and len(labels) != 1:
        parser.error("--watch supports exactly one label at a time")

    try:
        return asyncio.run(deploy_all(labels, cfg, args.watch))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
