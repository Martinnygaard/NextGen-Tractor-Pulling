from pathlib import Path
from datetime import datetime, timezone
from typing import Literal
import json
import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


app = FastAPI(title="LEGO Tractor Pull Scoreboard")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_FILE = BASE_DIR / "sled_config.json"


class ScoreboardState(BaseModel):
    score: int = Field(default=0, ge=0, le=999)
    full_pull: bool = False
    scroll_offset: int = Field(default=0, ge=0)


class PullHistoryEntry(BaseModel):
    id: int
    timestamp: str
    tractor: str
    result_m: float = Field(ge=0, le=100)


class PullHistoryCreate(BaseModel):
    tractor: str = Field(min_length=1, max_length=60)
    result_m: float = Field(ge=0, le=100)
    timestamp: str | None = None


class SledRemoteCommand(BaseModel):
    action: Literal[
        "start_pull",
        "stop_pull",
        "home_weight",
        "set_mode",
        "set_weight_percent",
        "set_signal_red",
        "set_signal_green",
        "set_signal_green_blink",
        "clear_signal",
        "set_ramp_end_m",
        "set_full_rotations",
    ]
    value: float | None = None


class SledConfig(BaseModel):
    ramp_end_m: float = Field(default=70.0, ge=5.0, le=100.0)
    full_rotations: float = Field(default=43.0, ge=1.0, le=200.0)


class ScoreboardRemoteCommand(BaseModel):
    action: Literal["set_score", "full_pull", "reset", "blank"]
    value: int | None = None


class CommandEnvelope(BaseModel):
    id: int
    timestamp: str
    source: str
    payload: dict


class LiveState(BaseModel):
    distance_m: float = Field(default=0, ge=0, le=100)
    scoreboard: ScoreboardState
    last_sled_command: CommandEnvelope | None = None
    last_scoreboard_command: CommandEnvelope | None = None
    sled_pending_commands: int = 0
    scoreboard_pending_commands: int = 0
    history_count: int


state = ScoreboardState()
distance_m = 0.0
history: list[PullHistoryEntry] = []
command_seq = 1
history_seq = 1
last_sled_command: CommandEnvelope | None = None
last_scoreboard_command: CommandEnvelope | None = None
sled_commands: list[CommandEnvelope] = []
scoreboard_commands: list[CommandEnvelope] = []
last_sled_ack_id = 0
last_scoreboard_ack_id = 0


def load_sled_config() -> SledConfig:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return SledConfig(**data)
    except Exception:
        return SledConfig()


def save_sled_config(cfg: SledConfig) -> None:
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump(cfg.model_dump(), fh, indent=2)
    except Exception:
        pass


sled_config: SledConfig = load_sled_config()


class HubStatus(BaseModel):
    label: str
    name: str = ""
    connected: bool = False
    error: str | None = None
    ts: float = 0.0


class BridgeStatusUpdate(BaseModel):
    hubs: list[HubStatus] = []


bridge_hubs: list[HubStatus] = []
bridge_status_ts: float = 0.0
reconnect_requests: set[str] = set()
reboot_requests: set[str] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_command_id() -> int:
    global command_seq
    value = command_seq
    command_seq += 1
    return value


def next_history_id() -> int:
    global history_seq
    value = history_seq
    history_seq += 1
    return value


def enqueue_command(target: Literal["sled", "scoreboard"], payload: dict) -> CommandEnvelope:
    global last_sled_command
    global last_scoreboard_command

    envelope = CommandEnvelope(
        id=next_command_id(),
        timestamp=now_iso(),
        source="web",
        payload=payload,
    )

    if target == "sled":
        sled_commands.append(envelope)
        last_sled_command = envelope
    else:
        scoreboard_commands.append(envelope)
        last_scoreboard_command = envelope

    return envelope


def command_list_for_target(target: Literal["sled", "scoreboard"]) -> list[CommandEnvelope]:
    if target == "sled":
        return sled_commands
    return scoreboard_commands


def ack_for_target(target: Literal["sled", "scoreboard"]) -> int:
    if target == "sled":
        return last_sled_ack_id
    return last_scoreboard_ack_id


def pending_count(target: Literal["sled", "scoreboard"]) -> int:
    queue = command_list_for_target(target)
    ack_id = ack_for_target(target)
    count = 0
    for cmd in queue:
        if cmd.id > ack_id:
            count += 1
    return count


@app.get("/api/state")
def get_state() -> ScoreboardState:
    return state


@app.get("/api/live")
def get_live_state() -> LiveState:
    return LiveState(
        distance_m=distance_m,
        scoreboard=state,
        last_sled_command=last_sled_command,
        last_scoreboard_command=last_scoreboard_command,
        sled_pending_commands=pending_count("sled"),
        scoreboard_pending_commands=pending_count("scoreboard"),
        history_count=len(history),
    )


@app.post("/api/state")
def set_state(next_state: ScoreboardState) -> ScoreboardState:
    global state
    state = next_state
    return state


@app.post("/api/score/{score}")
def set_score(score: int) -> ScoreboardState:
    global state
    state = ScoreboardState(score=max(0, min(999, score)), full_pull=score >= 100)
    return state


@app.post("/api/full-pull")
def full_pull() -> ScoreboardState:
    global state
    state.full_pull = True
    return state


@app.post("/api/reset")
def reset() -> ScoreboardState:
    global state
    state = ScoreboardState()
    return state


@app.get("/api/distance")
def get_distance() -> dict:
    return {"distance_m": distance_m}


@app.post("/api/distance/{next_distance}")
def set_distance(next_distance: float) -> dict:
    global distance_m
    distance_m = max(0.0, min(100.0, next_distance))
    return {"distance_m": distance_m}


@app.get("/api/history")
def get_history() -> list[PullHistoryEntry]:
    return history


@app.post("/api/history")
def add_history(entry: PullHistoryCreate) -> PullHistoryEntry:
    row = PullHistoryEntry(
        id=next_history_id(),
        timestamp=entry.timestamp or now_iso(),
        tractor=entry.tractor.strip(),
        result_m=entry.result_m,
    )
    history.insert(0, row)
    return row


@app.delete("/api/history")
def clear_history() -> dict:
    history.clear()
    return {"ok": True, "count": 0}


@app.post("/api/remote/sled")
def remote_sled(command: SledRemoteCommand) -> CommandEnvelope:
    return enqueue_command("sled", command.model_dump())


@app.post("/api/remote/scoreboard")
def remote_scoreboard(command: ScoreboardRemoteCommand) -> CommandEnvelope:
    global state

    if command.action == "set_score":
        score = int(command.value or 0)
        state = ScoreboardState(score=max(0, min(999, score)), full_pull=score >= 100)
    elif command.action == "full_pull":
        state.full_pull = True
    elif command.action == "blank":
        state = ScoreboardState(score=0, full_pull=False, scroll_offset=0)
    else:
        state = ScoreboardState()

    return enqueue_command("scoreboard", command.model_dump())


@app.get("/api/remote/{target}/next")
def remote_next(
    target: Literal["sled", "scoreboard"],
    after_id: int = 0,
) -> CommandEnvelope | None:
    queue = command_list_for_target(target)
    for cmd in queue:
        if cmd.id > after_id:
            return cmd
    return None


@app.get("/api/remote/{target}/pending")
def remote_pending(
    target: Literal["sled", "scoreboard"],
    after_id: int = 0,
    limit: int = 25,
) -> list[CommandEnvelope]:
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    queue = command_list_for_target(target)
    out: list[CommandEnvelope] = []
    for cmd in queue:
        if cmd.id > after_id:
            out.append(cmd)
            if len(out) >= limit:
                break
    return out


@app.post("/api/remote/{target}/ack/{command_id}")
def remote_ack(
    target: Literal["sled", "scoreboard"],
    command_id: int,
) -> dict:
    global last_sled_ack_id
    global last_scoreboard_ack_id

    if target == "sled":
        if command_id > last_sled_ack_id:
            last_sled_ack_id = command_id
        while len(sled_commands) > 0 and sled_commands[0].id <= last_sled_ack_id:
            sled_commands.pop(0)
        return {
            "ok": True,
            "target": "sled",
            "ack_id": last_sled_ack_id,
            "pending": pending_count("sled"),
        }

    if command_id > last_scoreboard_ack_id:
        last_scoreboard_ack_id = command_id
    while len(scoreboard_commands) > 0 and scoreboard_commands[0].id <= last_scoreboard_ack_id:
        scoreboard_commands.pop(0)
    return {
        "ok": True,
        "target": "scoreboard",
        "ack_id": last_scoreboard_ack_id,
        "pending": pending_count("scoreboard"),
    }


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "scoreboard-server"}


@app.get("/api/sled-config")
def get_sled_config() -> SledConfig:
    return sled_config


def _enqueue_sled_config_commands(cfg: SledConfig) -> None:
    enqueue_command("sled", {"action": "set_ramp_end_m", "value": cfg.ramp_end_m})
    enqueue_command("sled", {"action": "set_full_rotations", "value": cfg.full_rotations})


@app.post("/api/sled-config")
def set_sled_config(cfg: SledConfig) -> SledConfig:
    global sled_config
    sled_config = cfg
    save_sled_config(sled_config)
    _enqueue_sled_config_commands(sled_config)
    return sled_config


@app.post("/api/sled-config/push")
def push_sled_config() -> SledConfig:
    """Re-enqueue current config to sled without changing values.
    Bridge calls this after sled program (re)starts."""
    _enqueue_sled_config_commands(sled_config)
    return sled_config


@app.get("/api/bridge-status")
def get_bridge_status() -> dict:
    age = (time.time() - bridge_status_ts) if bridge_status_ts else None
    return {
        "hubs": [h.model_dump() for h in bridge_hubs],
        "updated_at": bridge_status_ts,
        "age_seconds": age,
        "stale": (age is None) or (age > 10),
    }


@app.post("/api/bridge-status")
def post_bridge_status(payload: BridgeStatusUpdate) -> dict:
    global bridge_hubs, bridge_status_ts
    bridge_hubs = list(payload.hubs)
    bridge_status_ts = time.time()
    return {"ok": True}


@app.post("/api/bridge-control/reconnect/{label}")
def request_reconnect(label: str) -> dict:
    reconnect_requests.add(label)
    return {"ok": True, "label": label, "pending": sorted(reconnect_requests)}


@app.post("/api/bridge-control/reboot/{label}")
def request_reboot(label: str) -> dict:
    reboot_requests.add(label)
    return {"ok": True, "label": label, "pending": sorted(reboot_requests)}


@app.get("/api/bridge-control")
def get_bridge_control() -> dict:
    return {
        "reconnect": sorted(reconnect_requests),
        "reboot": sorted(reboot_requests),
    }


@app.post("/api/bridge-control/ack/{kind}/{label}")
def ack_control(kind: str, label: str) -> dict:
    if kind == "reconnect":
        reconnect_requests.discard(label)
    elif kind == "reboot":
        reboot_requests.discard(label)
    else:
        return {"ok": False, "error": "unknown kind"}
    return {"ok": True, "kind": kind, "label": label}


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

