#!/usr/bin/env python3
"""Run a player-written drone script against a challenge and return a JSON trace.

    python3 drone_runner.py <script.py> <challenge_id> [--json] [--dry-run] [--no-commit]

The script runs in a separate Python process (``python -E``, PYTHON* env ignored) with a
timeout (5 s by default), a stripped environment, and CPU/memory limits on
POSIX. Every ``station_api`` call appends an action frame; this runner then
validates the outcome, deducts Cognitive Bandwidth, and on a pass commits the
solution with git, checks off the linked benchmark, and rebuilds the résumé.

Challenge ids: c1_loops, c2_csv, c3_graph, c4_numpy, c5_schelling, free.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
import traceback
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_TIMEOUT = float(os.environ.get("PRAXIS_DRONE_TIMEOUT", "5"))
# Challenge 2 imports pandas + matplotlib, whose first import can be slow.
CHALLENGE_TIMEOUTS = {"c2_csv": max(DEFAULT_TIMEOUT, 15.0), "c4_numpy": max(DEFAULT_TIMEOUT, 8.0)}

# ==========================================================================
# Child-process mode: actually execute the player's script
# ==========================================================================


def _exec_child(script: str) -> int:
    import runpy

    script_path = Path(script).resolve()
    sys.path.insert(0, str(script_path.parent))
    sys.argv = [str(script_path)]
    import station_api as S

    try:
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    except S.OutOfBandwidth:
        return 3
    except SystemExit as e:
        return int(e.code or 0) if isinstance(e.code, int) else 0
    except BaseException as e:  # report the player's error as a frame
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        # hide runner/runpy frames, keep the player's
        keep = [l for l in tb if "runpy.py" not in l and "drone_runner.py" not in l]
        S._emit({"action": "error", "pos": list(S._STATE["pos"]), "bandwidth_cost": 0,
                 "log": f"{type(e).__name__}: {e}", "traceback": "".join(keep)[-4000:]})
        return 1


# ==========================================================================
# Challenge worlds
# ==========================================================================

C3_MAZE = [  # row 0 is the TOP (y = 6)
    "...#...",
    ".#.#.#.",
    ".#...#.",
    ".####..",
    "......#",
    "#.##.#.",
    ".......",
]
C3_GRAPH = {
    "Ada": ["Ben", "Cy", "Dee", "Eli", "Mark"],
    "Ben": ["Ada", "Cy", "Dee", "Eli"],
    "Cy": ["Ada", "Ben", "Dee", "Eli"],
    "Dee": ["Ada", "Ben", "Cy", "Eli"],
    "Eli": ["Ada", "Ben", "Cy", "Dee"],
    "Fay": ["Gus", "Hal", "Ivy", "Jo", "Mark"],
    "Gus": ["Fay", "Hal", "Ivy", "Jo"],
    "Hal": ["Fay", "Gus", "Ivy", "Jo"],
    "Ivy": ["Fay", "Gus", "Hal", "Jo"],
    "Jo": ["Fay", "Gus", "Hal", "Ivy"],
    "Mark": ["Ada", "Fay"],
}
C3_POSITIONS = {
    "Ada": [2, 4], "Ben": [0, 6], "Cy": [0, 3], "Dee": [2, 6], "Eli": [4, 4],
    "Fay": [6, 2], "Gus": [6, 0], "Hal": [4, 0], "Ivy": [3, 2], "Jo": [1, 1],
    "Mark": [6, 6],
}


def c3_walls() -> set[tuple[int, int]]:
    h = len(C3_MAZE)
    return {(x, h - 1 - r) for r, row in enumerate(C3_MAZE) for x, ch in enumerate(row) if ch == "#"}


def build_world(challenge: str, effects: dict, state: dict) -> dict:
    import common as C

    world: dict = {
        "challenge": challenge,
        "drone": [0, 0],
        "bandwidth": float(state["cognitive_bandwidth"]),
        "cost_mult": effects.get("bandwidth_cost_mult", 1.0),
        "sensors": effects.get("sensors", []),
        "assets": str(C.ASSETS),
        "tiles": {},
        "data": {},
    }
    if challenge == "c1_loops":
        rng = random.Random(101)
        world["size"] = [5, 5]
        for x in range(5):
            for y in range(5):
                world["tiles"][f"{x},{y}"] = {"type": "respondent", "value": round(rng.uniform(1, 10), 1),
                                              "harvested": False}
    elif challenge == "c2_csv":
        world["size"] = [3, 3]
        world["drone"] = [1, 1]
        world["tiles"]["1,1"] = {"type": "data_terminal", "value": "survey_stage1.csv"}
        world["data"]["csv"] = str(C.ASSETS / "survey_stage1.csv")
    elif challenge == "c3_graph":
        world["size"] = [7, 7]
        for (x, y) in c3_walls():
            world["tiles"][f"{x},{y}"] = {"type": "wall"}
        for name, (x, y) in C3_POSITIONS.items():
            world["tiles"][f"{x},{y}"] = {"type": "person", "node": name, "value": name,
                                          "degree": len(C3_GRAPH[name])}
        world["data"]["graph"] = C3_GRAPH
        world["data"]["positions"] = C3_POSITIONS
    elif challenge == "c4_numpy":
        rng = random.Random(404)
        world["size"] = [5, 5]
        X, y = [], []
        for gx in range(5):
            for gy in range(5):
                soil, rain = round(rng.uniform(0, 10), 2), round(rng.uniform(0, 10), 2)
                yield_ = round(1.8 * soil - 0.9 * rain + 4 + rng.gauss(0, 1), 3)
                X.append([soil, rain])
                y.append(yield_)
                world["tiles"][f"{gx},{gy}"] = {"type": "plot", "soil": soil, "rain": rain, "value": yield_}
        Xt, yt = [], []
        for _ in range(12):
            soil, rain = round(rng.uniform(0, 10), 2), round(rng.uniform(0, 10), 2)
            Xt.append([soil, rain])
            yt.append(round(1.8 * soil - 0.9 * rain + 4 + rng.gauss(0, 1), 3))
        world["data"].update({"X_train": X, "y_train": y, "X_test": Xt})
        world["_hidden"] = {"y_test": yt}
    elif challenge == "c5_schelling":
        rng = random.Random(1971)
        n = 10
        world["size"] = [n, n]
        cells = [1] * 45 + [2] * 45 + [0] * 10
        rng.shuffle(cells)
        grid = [cells[r * n:(r + 1) * n] for r in range(n)]
        world["data"]["abm"] = grid
        world["data"]["abm_seed"] = 1971
        for y in range(n):
            for x in range(n):
                if grid[y][x]:
                    world["tiles"][f"{x},{y}"] = {"type": f"agent_{grid[y][x]}", "value": grid[y][x]}
    elif challenge == "free":
        n = int(effects.get("grid_size", 3))
        rng = random.Random(int(time.time()) // 86400)
        world["size"] = [n, n]
        for x in range(n):
            for y in range(n):
                r = rng.random()
                if r < 0.65:
                    t = {"type": "respondent", "value": round(rng.uniform(1, 10), 1), "harvested": False}
                    if r < 0.12:
                        t.update({"corrupt": True, "_clean_value": t["value"], "value": None})
                    if "stats" in world["sensors"]:
                        t["p_value"] = round(rng.uniform(0.001, 0.2), 3)
                    world["tiles"][f"{x},{y}"] = t
                elif r < 0.75:
                    world["tiles"][f"{x},{y}"] = {"type": "anomaly", "value": "A philosophical anomaly hums here."}
    else:
        raise ValueError(f"Unknown challenge {challenge!r}")
    return world


# ==========================================================================
# Reference computations (validators never trust the player's process)
# ==========================================================================


def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, EPS, FPMIN = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > FPMIN else FPMIN)
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > FPMIN else FPMIN)
        c = 1 + aa / c
        c = c if abs(c) > FPMIN else FPMIN
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > FPMIN else FPMIN)
        c = 1 + aa / c
        c = c if abs(c) > FPMIN else FPMIN
        de = d * c
        h *= de
        if abs(de - 1) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(lbt)
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def welch_t_test(a: list[float], b: list[float]) -> tuple[float, float]:
    """Two-sided Welch t-test. Returns (t, p)."""
    na, nb = len(a), len(b)
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se2 = va / na + vb / nb
    t = (ma - mb) / math.sqrt(se2)
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = _betai(df / 2, 0.5, df / (df + t * t))
    return t, p


def survey_reference(csv_path: str) -> dict:
    import csv

    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                w = float(r["wellbeing_score"])
                h = float(r["hours_social_media"])
            except (ValueError, TypeError):
                continue
            if w != w or h != h:
                continue
            rows.append((r["group"], w))
    vals = [w for _, w in rows]
    n = len(vals)
    mean = sum(vals) / n
    std1 = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))
    std0 = math.sqrt(sum((v - mean) ** 2 for v in vals) / n)
    t, p = welch_t_test([w for g, w in rows if g == "treatment"], [w for g, w in rows if g == "control"])
    return {"n": n, "mean": mean, "std": std1, "std_population": std0, "t": t, "p_value": p}


def betweenness(graph: dict[str, list[str]]) -> dict[str, float]:
    """Brandes' algorithm, unweighted, undirected."""
    cb = dict.fromkeys(graph, 0.0)
    for s in graph:
        stack, pred = [], {v: [] for v in graph}
        sigma = dict.fromkeys(graph, 0)
        dist = dict.fromkeys(graph, -1)
        sigma[s], dist[s] = 1, 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in graph[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = dict.fromkeys(graph, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                cb[w] += delta[w]
    return {k: v / 2 for k, v in cb.items()}


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def ols(X: list[list[float]], y: list[float]) -> list[float]:
    Xa = [[1.0, *r] for r in X]
    k = len(Xa[0])
    XtX = [[sum(r[i] * r[j] for r in Xa) for j in range(k)] for i in range(k)]
    Xty = [sum(r[i] * yy for r, yy in zip(Xa, y)) for i in range(k)]
    return _solve(XtX, Xty)  # [bias, w1, w2]


def mse(pred: list[float], truth: list[float]) -> float:
    return sum((p - t) ** 2 for p, t in zip(pred, truth)) / len(truth)


# ==========================================================================
# Validation
# ==========================================================================


def _last_submission(frames: list[dict]) -> dict | None:
    subs = [f.get("result") for f in frames if f.get("action") == "submit_result"]
    return subs[-1] if subs else None


def _num(d: dict, *keys: str) -> float | None:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                return None
    return None


def validate(challenge: str, world: dict, frames: list[dict], started: float) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    sub = _last_submission(frames) or {}
    if challenge == "c1_loops":
        harvested = {tuple(f["pos"]) for f in frames if f.get("action") == "harvest_data" and f.get("value") is not None}
        need = {(x, y) for x in range(5) for y in range(5)}
        missing = need - harvested
        if missing:
            msgs.append(f"{len(need) - len(missing)}/25 respondents sampled. Missing e.g. {sorted(missing)[:3]}.")
            return False, msgs
        msgs.append("All 25 respondents sampled.")
        return True, msgs
    if challenge == "c2_csv":
        ref = survey_reference(world["data"]["csv"])
        ok = True
        mean, std, p = _num(sub, "mean"), _num(sub, "std", "sd"), _num(sub, "p_value", "p")
        if mean is None or abs(mean - ref["mean"]) > 0.05:
            ok = False
            msgs.append(f"mean: expected ≈{ref['mean']:.3f} on cleaned rows (n={ref['n']}), got {mean}")
        if std is None or min(abs(std - ref["std"]), abs(std - ref["std_population"])) > 0.05:
            ok = False
            msgs.append(f"std: expected ≈{ref['std']:.3f}, got {std}")
        if p is None or abs(p - ref["p_value"]) > max(0.005, 0.05 * ref["p_value"]):
            ok = False
            msgs.append(f"p_value (Welch t-test treatment vs control): expected ≈{ref['p_value']:.4g}, got {p}")
        plots = [f for f in frames if f.get("action") == "plot_csv"]
        png = Path(world["assets"]) / "stage1_plot.png"
        if not plots and not (png.exists() and png.stat().st_mtime >= started - 1):
            ok = False
            msgs.append("No plot saved — call plot_csv(...) (writes _assets/stage1_plot.png).")
        if ok:
            msgs.append(f"Stats verified on n={ref['n']} clean rows: mean={ref['mean']:.2f}, "
                        f"std={ref['std']:.2f}, p={ref['p_value']:.3g}.")
        return ok, msgs
    if challenge == "c3_graph":
        bc = betweenness(world["data"]["graph"])
        broker = max(bc, key=bc.get)
        answer = sub.get("value", sub.get("node"))
        ok = True
        if answer != broker:
            ok = False
            msgs.append(f"Submitted {answer!r}; that is not the highest-betweenness node.")
        bx, by = world["data"]["positions"][broker]
        visited = any(f.get("action") == "harvest_data" and f.get("pos") == [bx, by] for f in frames)
        if not visited:
            ok = False
            msgs.append("Fly the drone to the broker's tile and harvest_data() there (BFS around the walls).")
        if ok:
            msgs.append(f"{broker} bridges two clusters (betweenness {bc[broker]:.1f}) — a weak tie, per Granovetter.")
        return ok, msgs
    if challenge == "c4_numpy":
        preds = sub.get("predictions")
        truth = world["_hidden"]["y_test"]
        if not isinstance(preds, list) or len(preds) != len(truth):
            return False, [f"Submit predictions=[...] with {len(truth)} values for test_inputs()."]
        try:
            preds = [float(p) for p in preds]
        except (TypeError, ValueError):
            return False, ["predictions must be numbers."]
        b = ols(world["data"]["X_train"], world["data"]["y_train"])
        ref_pred = [b[0] + b[1] * r[0] + b[2] * r[1] for r in world["data"]["X_test"]]
        ref_mse, got = mse(ref_pred, truth), mse(preds, truth)
        limit = ref_mse * 1.25 + 0.25
        if got > limit:
            return False, [f"Test MSE {got:.3f} > {limit:.3f} (OLS reference {ref_mse:.3f}). Keep descending."]
        return True, [f"Test MSE {got:.3f} (OLS reference {ref_mse:.3f}). Gradient descent converged."]
    if challenge == "c5_schelling":
        import station_api as S

        steps = [f for f in frames if f.get("action") == "run_abm_step"]
        if not steps:
            return False, ["Call run_abm_step(rule) at least once."]
        initial = S.segregation_index(world["data"]["abm"])
        final_grid = [[int(c) for c in row] for row in steps[-1]["grid"]]
        counts = lambda g: (sum(r.count(1) for r in g), sum(r.count(2) for r in g))  # noqa: E731
        if counts(final_grid) != counts(world["data"]["abm"]):
            return False, ["Agent counts changed — agents may move, not vanish."]
        final = S.segregation_index(final_grid)
        if final - initial < 0.15:
            return False, [f"Segregation rose {initial:.2f} → {final:.2f}; need +0.15. Run more steps or rethink the rule."]
        return True, [f"Segregation {initial:.2f} → {final:.2f} after {len(steps)} steps: mild individual "
                      "preferences produced strong collective sorting. Write up why in 04 Writing/."]
    if challenge == "free":
        n = sum(1 for f in frames if f.get("action") == "harvest_data" and f.get("value") is not None)
        return False, [f"Free play: {n} samples harvested (no pass condition)."]
    return False, ["Unknown challenge"]


# ==========================================================================
# Orchestration
# ==========================================================================


def _limits(timeout: float):  # pragma: no cover - platform specific
    def apply():
        try:
            import resource

            cpu = int(math.ceil(timeout)) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            if sys.platform.startswith("linux"):
                resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
        except Exception:
            pass
        os.setsid() if hasattr(os, "setsid") else None
    return apply if os.name == "posix" else None


def resolve_script(script: str) -> Path:
    import common as C

    p = Path(script).expanduser()
    if not p.is_absolute():
        cand = C.DRONES / p
        p = cand if cand.exists() or not p.exists() else p.resolve()
    return p


def git_commit_solution(path: Path, message: str) -> str:
    import common as C

    if not C.git_available():
        return "git not installed — solution not committed"
    top = C.run_git(["rev-parse", "--show-toplevel"], path.parent)
    if top.returncode != 0:
        C.run_git(["init", "-q"], path.parent)
        repo = path.parent
    else:
        repo = Path(top.stdout.strip())
    C.run_git(["add", "--", str(path)], repo)
    res = C.run_git(["commit", "-q", "-m", message, "--", str(path)], repo)
    if res.returncode != 0:
        out = (res.stdout + res.stderr).strip()
        if "nothing to commit" in out or "no changes added" in out or "nothing added" in out:
            return f"Solution already committed in {C.rel(repo)}"
        return f"git commit failed: {out[-300:]}"
    sha = C.run_git(["rev-parse", "--short", "HEAD"], repo).stdout.strip()
    return f"Committed solution to {C.rel(repo) or '.'} ({sha})"


def run_drone(script: str, challenge: str, dry_run: bool = False, commit: bool = True,
              timeout: float | None = None) -> dict:
    import common as C

    state = C.load_state()
    effects = C.recompute_tech_effects(state)
    man = C.manifest()
    chall = next((c for c in man.get("challenges") or [] if c["id"] == challenge), None)
    if challenge != "free" and chall is None:
        raise C.PraxisError(f"Unknown challenge {challenge!r}. Known: " +
                            ", ".join(c["id"] for c in man.get("challenges") or []) + ", free")
    missing_tech = [t for t in (chall or {}).get("requires_tech") or [] if t not in state["unlocked_tech"]]
    if missing_tech:
        return {"success": False, "challenge_passed": False, "frames": [], "locked": True,
                "error": f"Locked: requires tech {', '.join(missing_tech)}",
                "message": f"Challenge {challenge} is locked. Unlock {', '.join(missing_tech)} first."}
    if state["cognitive_bandwidth"] <= 0:
        return {"success": False, "challenge_passed": False, "frames": [], "out_of_bandwidth": True,
                "error": "Out of Cognitive Bandwidth",
                "message": "0 Cognitive Bandwidth. Run `learn start` (deep work) or `learn quiz` to recharge."}
    path = resolve_script(script)
    if not path.exists():
        raise C.PraxisError(f"Drone script not found: {path}")
    if challenge == "c2_csv" and not (C.ASSETS / "survey_stage1.csv").exists():
        import gen_assets

        gen_assets.make_survey()

    world = build_world(challenge, effects, state)
    hidden = world.pop("_hidden", None)
    tmpdir = Path(tempfile.mkdtemp(prefix="praxis_drone_"))
    world_file, trace_file = tmpdir / "world.json", tmpdir / "trace.jsonl"
    world_file.write_text(json.dumps(world), encoding="utf-8")
    trace_file.write_text("", encoding="utf-8")
    if hidden:
        world["_hidden"] = hidden

    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT") if k in os.environ}
    env.update({"PRAXIS_WORLD": str(world_file), "PRAXIS_TRACE": str(trace_file), "MPLBACKEND": "Agg",
                "PYTHONDONTWRITEBYTECODE": "1"})
    to = timeout or CHALLENGE_TIMEOUTS.get(challenge, DEFAULT_TIMEOUT)
    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run([C.python_exe(), "-E", str(HERE / "drone_runner.py"), "--exec", str(path)],
                              cwd=str(path.parent), env=env, capture_output=True, text=True, timeout=to,
                              preexec_fn=_limits(to))
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = -9
        stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
    elapsed = round(time.time() - started, 3)

    frames = []
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    for p in (world_file, trace_file):
        p.unlink(missing_ok=True)
    tmpdir.rmdir()

    errors = [f for f in frames if f.get("action") == "error"]
    if timed_out:
        frames.append({"step": len(frames) + 1, "action": "error", "pos": frames[-1]["pos"] if frames else world["drone"],
                       "bandwidth_cost": 0, "log": f"Timed out after {to:.0f}s — infinite loop?"})
    spent = round(sum(float(f.get("bandwidth_cost", 0)) for f in frames), 2)
    passed, notes = (False, ["Script crashed — see the error frame."]) if errors or timed_out else \
        validate(challenge, world, frames, started)
    if rc == 3:
        notes.insert(0, "Drone halted: out of Cognitive Bandwidth.")

    result: dict = {
        "success": not errors and not timed_out,
        "challenge": challenge,
        "script": C.rel(path),
        "frames": frames,
        "challenge_passed": passed,
        "notes": notes,
        "bandwidth_spent": spent,
        "elapsed_s": elapsed,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "timed_out": timed_out,
        "world": {"size": world["size"], "drone": world["drone"], "tiles": world["tiles"]},
        "unlocked_benchmark": None,
        "unlocked_tech": [],
        "git_commit": None,
        "dry_run": dry_run,
    }
    image = next((f["image"] for f in reversed(frames) if f.get("image")), None)
    if image:
        result["image"] = image

    if dry_run:
        result["message"] = f"[dry-run] {challenge}: {'PASS' if passed else 'FAIL'} — " + " ".join(notes)
        return result

    state = C.load_state()
    state["cognitive_bandwidth"] = state["cognitive_bandwidth"] - spent
    C.clamp_bandwidth(state)
    state["lifetime_stats"]["drone_runs"] = state["lifetime_stats"].get("drone_runs", 0) + 1
    C.touch_streak(state)
    if passed:
        first = challenge not in state["lifetime_stats"]["challenges_passed"]
        if first:
            state["lifetime_stats"]["challenges_passed"].append(challenge)
            state["xp"] += int(C.rewards()["challenge_xp"])
        result["unlocked_tech"] = C.award_source(state, challenge)
        bench = (chall or {}).get("benchmark")
        if bench:
            done = C.complete_item(state, bench, True)
            result["unlocked_benchmark"] = bench
            result["unlocked_tech"] = C.unique(result["unlocked_tech"] + done["unlocked_tech"])
            result["stage_advanced_to"] = done["stage_advanced_to"]
        C.save_state(state)
        if commit:
            result["git_commit"] = git_commit_solution(path, f"drone: {challenge} passed" + (f" ({bench})" if bench else ""))
        result["portfolio"] = C.rebuild_portfolio() if bench else None
    else:
        C.save_state(state)
    result["cognitive_bandwidth"] = state["cognitive_bandwidth"]
    result["message"] = f"{challenge}: {'PASS ✅' if passed else 'FAIL ❌'} — " + " ".join(notes)
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--exec":
        return _exec_child(argv[1])
    import common as C

    ap = argparse.ArgumentParser(description="Run a drone script against a Praxis challenge.")
    ap.add_argument("script")
    ap.add_argument("challenge")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--timeout", type=float)
    a = ap.parse_args(argv)
    try:
        res = run_drone(a.script, a.challenge, a.dry_run, not a.no_commit, a.timeout)
    except C.PraxisError as e:
        res = {"success": False, "challenge_passed": False, "frames": [], "error": str(e), "message": f"Error: {e}"}
    if a.json:
        C.emit(res, True)
    else:
        for f in res.get("frames", []):
            print(f"  [{f['step']:>3}] {f.get('log', f['action'])}")
            if f.get("traceback"):
                print(f["traceback"])
        if res.get("stdout"):
            print("--- stdout ---\n" + res["stdout"].rstrip())
        print(res.get("message", ""))
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
