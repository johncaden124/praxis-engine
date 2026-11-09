"""station_api — the Python API your research drone understands.

Import it from any drone script in ``code/drones/``::

    from station_api import move, scan, harvest_data, clean_outlier, \
        run_abm_step, plot_csv, submit_result

Scripts are run by ``_scripts/drone_runner.py`` (or the "Run & Commit"
button in the Godot game). Every call below records an action frame that
the game animates step by step, and most calls cost Cognitive Bandwidth.
When bandwidth runs out the drone stops — recharge it with a real study
session (``learn start`` / ``learn stop``) or a flashcard quiz.

Run a script outside the runner (``python3 my_drone.py``) and the API falls
back to an offline 5x5 practice world so you can debug in VS Code.

Coordinates: (x, y) with (0, 0) bottom-left. ``"N"`` is +y, ``"E"`` is +x.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "move", "scan", "harvest_data", "clean_outlier", "run_abm_step", "plot_csv",
    "submit_result", "get_pos", "world_size", "bandwidth", "log", "dataset_path",
    "graph", "node_pos", "is_wall", "training_data", "test_inputs", "abm_grid",
    "OutOfBandwidth", "DroneError",
]

DIRS = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
COSTS = {"move": 1, "scan": 1, "harvest_data": 1, "clean_outlier": 2, "run_abm_step": 3,
         "plot_csv": 5, "submit_result": 0, "log": 0}
MAX_FRAMES = 5000


class OutOfBandwidth(RuntimeError):
    """Raised when the drone has no Cognitive Bandwidth left."""


class DroneError(RuntimeError):
    """Raised for invalid drone commands."""


# --------------------------------------------------------------------------
# World loading
# --------------------------------------------------------------------------


def _practice_world() -> dict:
    rng = random.Random(7)
    tiles = {}
    for x in range(5):
        for y in range(5):
            tiles[f"{x},{y}"] = {"type": "respondent", "value": round(rng.uniform(1, 10), 2), "harvested": False}
    return {"challenge": "practice", "size": [5, 5], "drone": [0, 0], "tiles": tiles,
            "bandwidth": 10_000, "cost_mult": 1.0, "sensors": ["stats"], "data": {}, "assets": "."}


def _load_world() -> dict:
    p = os.environ.get("PRAXIS_WORLD")
    if p and Path(p).exists():
        return json.loads(Path(p).read_text(encoding="utf-8"))
    return _practice_world()


_WORLD = _load_world()
_TRACE_PATH = os.environ.get("PRAXIS_TRACE")
_STATE = {
    "pos": list(_WORLD.get("drone", [0, 0])),
    "bandwidth": float(_WORLD.get("bandwidth", 100)),
    "spent": 0.0,
    "step": 0,
}
_OFFLINE = _TRACE_PATH is None


def _emit(frame: dict) -> None:
    _STATE["step"] += 1
    frame = {"step": _STATE["step"], **frame}
    if _OFFLINE:
        print(f"[drone] {frame.get('log', frame['action'])}")
        return
    with open(_TRACE_PATH, "a", encoding="utf-8") as f:  # type: ignore[arg-type]
        f.write(json.dumps(frame) + "\n")


def _charge(action: str) -> float:
    cost = round(COSTS.get(action, 1) * float(_WORLD.get("cost_mult", 1.0)), 3)
    if _STATE["step"] >= MAX_FRAMES:
        raise DroneError(f"Step limit reached ({MAX_FRAMES} frames). Is there an infinite loop?")
    if cost > 0 and _STATE["bandwidth"] - cost < 0:
        _emit({"action": "out_of_bandwidth", "pos": list(_STATE["pos"]), "bandwidth_cost": 0,
               "log": "Out of Cognitive Bandwidth — run a study session or a quiz to recharge."})
        raise OutOfBandwidth("Out of Cognitive Bandwidth")
    _STATE["bandwidth"] -= cost
    _STATE["spent"] += cost
    return cost


def _tile(pos: list[int] | tuple[int, int] | None = None) -> dict | None:
    x, y = pos or _STATE["pos"]
    return _WORLD["tiles"].get(f"{x},{y}")


def _has(sensor: str) -> bool:
    return sensor in (_WORLD.get("sensors") or [])


# --------------------------------------------------------------------------
# Core drone commands
# --------------------------------------------------------------------------


def get_pos() -> tuple[int, int]:
    """Current drone position (x, y)."""
    return tuple(_STATE["pos"])  # type: ignore[return-value]


def world_size() -> tuple[int, int]:
    """(width, height) of the current grid."""
    w, h = _WORLD["size"]
    return int(w), int(h)


def bandwidth() -> float:
    """Cognitive Bandwidth remaining for this run."""
    return round(_STATE["bandwidth"], 2)


def is_wall(x: int, y: int) -> bool:
    """True if (x, y) is outside the grid or blocked."""
    w, h = world_size()
    if not (0 <= x < w and 0 <= y < h):
        return True
    t = _WORLD["tiles"].get(f"{x},{y}")
    return bool(t and t.get("type") == "wall")


def move(direction: str) -> bool:
    """Move one tile "N", "S", "E" or "W". Returns False if blocked."""
    d = str(direction).upper()[:1]
    if d not in DIRS:
        raise DroneError(f"move() needs 'N', 'S', 'E' or 'W', got {direction!r}")
    cost = _charge("move")
    x, y = _STATE["pos"]
    nx, ny = x + DIRS[d][0], y + DIRS[d][1]
    if is_wall(nx, ny):
        _emit({"action": "bump", "dir": d, "pos": [x, y], "bandwidth_cost": cost,
               "log": f"Blocked moving {d} from ({x},{y})"})
        return False
    _STATE["pos"] = [nx, ny]
    _emit({"action": "move", "dir": d, "pos": [nx, ny], "bandwidth_cost": cost, "log": f"Moved to ({nx},{ny})"})
    return True


def scan() -> dict:
    """Inspect the current tile. Returns a dict (type, value, flags...)."""
    cost = _charge("scan")
    t = dict(_tile() or {"type": "empty"})
    info = {k: v for k, v in t.items() if not k.startswith("_")}
    if not _has("stats"):
        info.pop("p_value", None)
    _emit({"action": "scan", "pos": list(_STATE["pos"]), "bandwidth_cost": cost,
           "tile": info, "log": f"Scanned {info.get('type')} at {tuple(_STATE['pos'])}"})
    return info


def harvest_data() -> float | None:
    """Collect the data sample on this tile. Returns its value (or None)."""
    cost = _charge("harvest_data")
    t = _tile()
    pos = list(_STATE["pos"])
    if not t or t.get("type") in ("wall", "empty"):
        _emit({"action": "harvest_data", "pos": pos, "value": None, "bandwidth_cost": cost,
               "log": "Nothing to harvest here"})
        return None
    if t.get("corrupt"):
        _emit({"action": "harvest_data", "pos": pos, "value": None, "bandwidth_cost": cost,
               "log": "Sample is corrupt — clean_outlier() first"})
        return None
    already = t.get("harvested", False)
    t["harvested"] = True
    val = t.get("value")
    msg = f"Re-sampled {val}" if already else f"Harvested {val}"
    if _has("stats") and "p_value" in t:
        msg += f" (p={t['p_value']})"
    _emit({"action": "harvest_data", "pos": pos, "value": val, "bandwidth_cost": cost, "log": msg,
           "node": t.get("node")})
    return val


def clean_outlier() -> bool:
    """Repair a corrupt / outlier sample on this tile. Returns True if cleaned."""
    cost = _charge("clean_outlier")
    t = _tile()
    pos = list(_STATE["pos"])
    if t and t.get("corrupt"):
        t["corrupt"] = False
        t["value"] = t.get("_clean_value", t.get("value"))
        _emit({"action": "clean_outlier", "pos": pos, "bandwidth_cost": cost, "log": f"Cleaned outlier at {tuple(pos)}"})
        return True
    _emit({"action": "clean_outlier", "pos": pos, "bandwidth_cost": cost, "log": "No outlier here"})
    return False


def log(message: Any) -> None:
    """Write a line to the in-game terminal (free)."""
    _emit({"action": "log", "pos": list(_STATE["pos"]), "bandwidth_cost": 0, "log": str(message)})


def submit_result(value: Any = None, **fields: Any) -> None:
    """Submit your answer for the current challenge (free). Call once at the end."""
    payload = fields if value is None else ({"value": value, **fields})
    try:
        json.dumps(payload)
    except TypeError:
        payload = json.loads(json.dumps(payload, default=_to_jsonable))
    _emit({"action": "submit_result", "pos": list(_STATE["pos"]), "bandwidth_cost": 0,
           "result": payload, "log": f"Submitted {', '.join(payload) or 'result'}"})


def _to_jsonable(o: Any) -> Any:
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


# --------------------------------------------------------------------------
# Data helpers
# --------------------------------------------------------------------------


def dataset_path(name: str = "survey_stage1.csv") -> str:
    """Absolute path of a dataset in the vault's _assets/ folder."""
    return str(Path(_WORLD.get("assets", ".")) / name)


def plot_csv(csv_path: str | None = None, x: str | None = None, y: str | None = None,
             out: str | None = None, kind: str = "auto", figure: Any = None) -> str:
    """Save a plot to _assets/ and show it in the game.

    Either pass a matplotlib ``figure`` you built yourself, or a CSV path plus
    column names: ``kind`` is "hist" (x only), "scatter" (x and y) or "auto".
    Returns the saved PNG path.
    """
    cost = _charge("plot_csv")
    out_path = Path(out) if out else Path(dataset_path("stage1_plot.png"))
    if not out_path.is_absolute():
        out_path = Path(dataset_path(str(out_path)))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if figure is None:
        import csv

        rows = list(csv.DictReader(open(csv_path or dataset_path(), encoding="utf-8")))

        def col(name: str) -> list[float]:
            vals = []
            for r in rows:
                try:
                    v = float(r[name])
                    if v == v:
                        vals.append(v)
                except (TypeError, ValueError, KeyError):
                    continue
            return vals

        figure, ax = plt.subplots(figsize=(6, 4), dpi=100)
        if y and kind in ("auto", "scatter"):
            pairs = []
            for r in rows:
                try:
                    a, b = float(r[x]), float(r[y])  # type: ignore[index]
                    if a == a and b == b:
                        pairs.append((a, b))
                except (TypeError, ValueError, KeyError):
                    continue
            ax.scatter([p[0] for p in pairs], [p[1] for p in pairs], s=10, alpha=0.6, color="#39d98a")
            ax.set_xlabel(x)
            ax.set_ylabel(y)
        else:
            ax.hist(col(x or "wellbeing_score"), bins=20, color="#39d98a", edgecolor="#0b1f17")
            ax.set_xlabel(x or "wellbeing_score")
            ax.set_ylabel("count")
        ax.set_title(Path(csv_path or dataset_path()).name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, bbox_inches="tight")
    plt.close(figure)
    _emit({"action": "plot_csv", "pos": list(_STATE["pos"]), "bandwidth_cost": cost,
           "image": str(out_path), "log": f"Saved plot {out_path.name}"})
    return str(out_path)


def graph() -> dict[str, list[str]]:
    """Social network for graph challenges: {node: [neighbors]}."""
    return {k: list(v) for k, v in (_WORLD.get("data", {}).get("graph") or {}).items()}


def node_pos(node: str) -> tuple[int, int]:
    """Grid tile where a person node lives."""
    p = (_WORLD.get("data", {}).get("positions") or {}).get(node)
    if p is None:
        raise DroneError(f"Unknown node {node!r}")
    return int(p[0]), int(p[1])


def training_data() -> tuple[list[list[float]], list[float]]:
    """(X, y) training data for the regression challenge."""
    d = _WORLD.get("data", {})
    return [list(r) for r in d.get("X_train", [])], list(d.get("y_train", []))


def test_inputs() -> list[list[float]]:
    """Feature rows you must predict yields for."""
    return [list(r) for r in _WORLD.get("data", {}).get("X_test", [])]


# --------------------------------------------------------------------------
# Agent-based modelling (Schelling)
# --------------------------------------------------------------------------


def abm_grid() -> list[list[int]]:
    """Copy of the ABM grid: 0 = empty, 1 / 2 = agent groups. grid[y][x]."""
    return [list(r) for r in _WORLD.get("data", {}).get("abm", [])]


def _neighbors(grid: list[list[int]], x: int, y: int) -> list[int]:
    h, w = len(grid), len(grid[0])
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx]:
                out.append(grid[ny][nx])
    return out


def segregation_index(grid: list[list[int]]) -> float:
    """Mean share of same-group neighbours across all agents (0..1)."""
    shares = []
    for y, row in enumerate(grid):
        for x, a in enumerate(row):
            if not a:
                continue
            nb = _neighbors(grid, x, y)
            if nb:
                shares.append(sum(1 for n in nb if n == a) / len(nb))
    return round(sum(shares) / len(shares), 4) if shares else 0.0


def run_abm_step(rule: Callable[[int, list[int]], bool] | None = None) -> dict:
    """Advance the Schelling model one step.

    ``rule(agent_group, neighbor_groups) -> bool`` returns True if the agent is
    unhappy and wants to move. Unhappy agents move to a random empty cell.
    Returns {"moved": n, "segregation": index}.
    """
    cost = _charge("run_abm_step")
    data = _WORLD.setdefault("data", {})
    grid = data.get("abm")
    if not grid:
        raise DroneError("This challenge has no agent grid.")
    rng = random.Random(data.get("abm_seed", 0) + _STATE["step"])
    if rule is None:
        def rule(a: int, nb: list[int]) -> bool:  # default: Schelling 30% threshold
            return bool(nb) and sum(1 for n in nb if n == a) / len(nb) < 0.3
    unhappy = []
    for y, row in enumerate(grid):
        for x, a in enumerate(row):
            if a and rule(a, _neighbors(grid, x, y)):
                unhappy.append((x, y))
    empties = [(x, y) for y, row in enumerate(grid) for x, a in enumerate(row) if not a]
    rng.shuffle(unhappy)
    moved = 0
    for (x, y) in unhappy:
        if not empties:
            break
        i = rng.randrange(len(empties))
        ex, ey = empties.pop(i)
        grid[ey][ex], grid[y][x] = grid[y][x], 0
        empties.append((x, y))
        moved += 1
    seg = segregation_index(grid)
    _emit({"action": "run_abm_step", "pos": list(_STATE["pos"]), "bandwidth_cost": cost,
           "moved": moved, "segregation": seg,
           "grid": ["".join(str(c) for c in row) for row in grid],
           "log": f"ABM step: {moved} agents moved, segregation={seg:.2f}"})
    return {"moved": moved, "segregation": seg}
