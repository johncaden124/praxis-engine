"""Shared helpers for the Praxis engine.

Everything here is curriculum-agnostic: paths are resolved relative to the
vault root, curricula are read from ``01 Plan/`` and the manifest, and all
state goes through atomic reads/writes of ``_scripts/state.json``.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def vault_root() -> Path:
    env = os.environ.get("PRAXIS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


ROOT = vault_root()
SCRIPTS = ROOT / "_scripts"
PLAN = ROOT / "01 Plan"
TODAY_DIR = ROOT / "02 Today"
READING = ROOT / "03 Reading"
WRITING = ROOT / "04 Writing"
QUESTIONS = ROOT / "05 Questions.md"
PEOPLE = ROOT / "06 People.md"
PROJECTS = ROOT / "07 Projects"
CARDS = ROOT / "08 Cards"
REVIEWS = ROOT / "09 Reviews"
PORTFOLIO = ROOT / "10 Portfolio"
CURRICULUMS = ROOT / "_curriculums"
TEMPLATES = ROOT / "_templates"
ASSETS = ROOT / "_assets"
CODE = ROOT / "code"
DRONES = CODE / "drones"
GAME = ROOT / "game"
STATE_FILE = SCRIPTS / "state.json"
SCHEDULE_FILE = SCRIPTS / "schedule.yaml"
CONFIG_FILE = SCRIPTS / "config.json"
BENCHMARKS = PLAN / "benchmarks.md"
GATHER = PLAN / "Gather List.md"
MANIFEST = PLAN / "curriculum_manifest.yaml"
STATE_MD = PLAN / "state.md"

VAULT_NAME_DEFAULT = "Learning"

# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------


def now() -> dt.datetime:
    """Current local time. PRAXIS_NOW (ISO) overrides it for tests."""
    fake = os.environ.get("PRAXIS_NOW")
    if fake:
        return dt.datetime.fromisoformat(fake)
    return dt.datetime.now().replace(microsecond=0)


def today() -> dt.date:
    return now().date()


def today_str() -> str:
    return today().isoformat()


def week_start(d: dt.date | None = None) -> str:
    d = d or today()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


# --------------------------------------------------------------------------
# YAML (PyYAML with a small fallback so `doctor` runs before pip install)
# --------------------------------------------------------------------------


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


def _mini_yaml(text: str) -> Any:
    """Very small YAML subset parser (maps, lists, flow maps/lists, scalars).

    Only used when PyYAML is missing; good enough for the engine's own files.
    """

    def scalar(v: str) -> Any:
        v = v.strip()
        if v == "" or v in ("null", "~"):
            return None
        if v in ("true", "false"):
            return v == "true"
        if v[0] in "\"'" and v[-1] == v[0]:
            return v[1:-1]
        if v.startswith("[") or v.startswith("{"):
            return flow(v)
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            return v

    def split_top(s: str) -> list[str]:
        parts, depth, cur, q = [], 0, "", None
        for ch in s:
            if q:
                cur += ch
                if ch == q:
                    q = None
                continue
            if ch in "\"'":
                q = ch
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        if cur.strip():
            parts.append(cur)
        return parts

    def flow(v: str) -> Any:
        v = v.strip()
        inner = v[1:-1]
        if v.startswith("["):
            return [scalar(p) for p in split_top(inner)]
        out = {}
        for p in split_top(inner):
            k, _, val = p.partition(":")
            out[k.strip().strip("\"'")] = scalar(val)
        return out

    lines = []
    folded_key = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = raw.split(" #")[0] if " #" in raw and '"' not in raw else raw
        lines.append(line.rstrip())

    def parse(i: int, indent: int) -> tuple[Any, int]:
        container: Any = None
        while i < len(lines):
            line = lines[i]
            ind = len(line) - len(line.lstrip())
            if ind < indent:
                break
            s = line.strip()
            if s.startswith("- "):
                if container is None:
                    container = []
                item = s[2:]
                if ":" in item and not item.startswith(("{", "[", '"')):
                    # list of maps: "- key: value"
                    k, _, val = item.partition(":")
                    obj = {k.strip(): scalar(val) if val.strip() else None}
                    i += 1
                    sub, i = parse(i, ind + 2)
                    if isinstance(sub, dict):
                        obj.update(sub)
                    container.append(obj)
                    continue
                container.append(scalar(item))
                i += 1
                continue
            k, _, val = s.partition(":")
            if container is None:
                container = {}
            key = k.strip().strip("\"'")
            if key.isdigit():
                key = int(key)
            val = val.strip()
            if val in (">", "|", ">-", "|-"):
                buf = []
                i += 1
                while i < len(lines) and (len(lines[i]) - len(lines[i].lstrip())) > ind:
                    buf.append(lines[i].strip())
                    i += 1
                container[key] = " ".join(buf)
                continue
            if val == "":
                i += 1
                sub, i = parse(i, ind + 1)
                container[key] = sub
                continue
            container[key] = scalar(val)
            i += 1
        return container, i

    del folded_key
    result, _ = parse(0, 0)
    return result


# --------------------------------------------------------------------------
# JSON state (atomic)
# --------------------------------------------------------------------------

DEFAULT_STATE: dict[str, Any] = {
    "curriculum_name": "Untitled Curriculum",
    "stage": 1,
    "xp": 0,
    "cognitive_bandwidth": 100,
    "max_bandwidth": 100,
    "streak_days": 0,
    "last_active_date": None,
    "active_session": {"running": False, "track": None, "target_file": None, "start_timestamp": None},
    "current_focus": {"reading": None, "course": None, "essay": None, "project": None},
    "weekly_stats": {
        "week_start": None,
        "hours_math": 0.0,
        "hours_coding": 0.0,
        "hours_reading": 0.0,
        "hours_writing": 0.0,
        "hours_discussion": 0.0,
        "pages_read": 0,
        "cards_due": 0,
        "cards_reviewed": 0,
    },
    "lifetime_stats": {
        "hours_math": 0.0,
        "hours_coding": 0.0,
        "hours_reading": 0.0,
        "hours_writing": 0.0,
        "hours_discussion": 0.0,
        "pages_read": 0,
        "cards_reviewed": 0,
        "drone_runs": 0,
        "challenges_passed": [],
    },
    "daily_log": {},
    "unlocked_tech": ["drone_move_basic", "grid_3x3"],
    "completed_benchmarks": [],
    "earned_credentials": [],
    "people_nodes": [],
}


def _merge_defaults(state: dict, defaults: dict) -> dict:
    for k, v in defaults.items():
        if k not in state:
            state[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(state[k], dict) and k not in ("daily_log",):
            _merge_defaults(state[k], v)
    return state


def load_state() -> dict:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = copy.deepcopy(DEFAULT_STATE)
    _merge_defaults(state, DEFAULT_STATE)
    roll_week(state)
    return state


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save_state(state: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    atomic_write(STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    write_state_md(state)


def write_state_md(state: dict) -> None:
    """Mirror key state fields into 01 Plan/state.md frontmatter for Dataview."""
    if not PLAN.exists():
        return
    stage_name = ""
    try:
        for st in manifest().get("stages", []):
            if int(st.get("stage")) == int(state["stage"]):
                stage_name = st.get("name", "")
    except Exception:
        pass
    fm = {
        "stage": state["stage"],
        "stage_name": stage_name,
        "active_book": state["current_focus"].get("reading") or "",
        "active_course": state["current_focus"].get("course") or "",
        "active_essay": state["current_focus"].get("essay") or "",
        "active_project": state["current_focus"].get("project") or "",
        "xp": state["xp"],
        "cognitive_bandwidth": state["cognitive_bandwidth"],
        "streak_days": state["streak_days"],
        "updated": today_str(),
    }
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, str) else v}")
    lines.append("---")
    body = (
        "\n# Current State\n\n"
        "This frontmatter mirrors `_scripts/state.json` (the live source of truth) so Dataview can show it.\n"
        "It is rewritten by `learn` after every state change — edit `state.json` or use the CLI instead of editing here.\n"
    )
    atomic_write(STATE_MD, "\n".join(lines) + "\n" + body)


def roll_week(state: dict) -> None:
    """Reset weekly_stats when a new ISO week starts (lifetime stats keep totals)."""
    ws = week_start()
    w = state["weekly_stats"]
    if w.get("week_start") != ws:
        cards_due = w.get("cards_due", 0)
        for k in list(w):
            if k.startswith("hours_"):
                w[k] = 0.0
        w["pages_read"] = 0
        w["cards_reviewed"] = 0
        w["cards_due"] = cards_due
        w["week_start"] = ws


def touch_streak(state: dict) -> None:
    """Call whenever the user does real work today."""
    t = today()
    last = state.get("last_active_date")
    if last == t.isoformat():
        return
    if last and dt.date.fromisoformat(last) == t - dt.timedelta(days=1):
        state["streak_days"] = int(state.get("streak_days", 0)) + 1
    else:
        state["streak_days"] = 1
    state["last_active_date"] = t.isoformat()


def log_day(state: dict, key: str, amount: float) -> None:
    day = state.setdefault("daily_log", {}).setdefault(today_str(), {})
    day[key] = round(day.get(key, 0) + amount, 2)


def clamp_bandwidth(state: dict) -> None:
    state["cognitive_bandwidth"] = round(max(0, min(state["max_bandwidth"], state["cognitive_bandwidth"])), 1)


def config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


# --------------------------------------------------------------------------
# Curriculum: manifest, schedule, benchmarks
# --------------------------------------------------------------------------


def manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    return load_yaml(MANIFEST) or {}


def schedule() -> dict:
    if not SCHEDULE_FILE.exists():
        return {}
    return load_yaml(SCHEDULE_FILE) or {}


def rewards() -> dict:
    base = {
        "xp_per_minute": 1,
        "bandwidth_per_minute": 0.5,
        "highlight_bandwidth": 10,
        "quiz_correct_bandwidth": 8,
        "person_xp": 15,
        "benchmark_xp": 250,
        "challenge_xp": 150,
    }
    base.update((schedule().get("rewards") or {}))
    return base


CHECK_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>[ xX])\] \(`(?P<id>[A-Za-z0-9_\-]+)`\)\s*(?P<text>.*)$")


def parse_checklist(path: Path) -> list[dict]:
    """Parse `- [ ] (`id`) text` lines with their nearest headings."""
    items: list[dict] = []
    if not path.exists():
        return items
    h2 = h3 = ""
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if line.startswith("## "):
            h2, h3 = line[3:].strip(), ""
        elif line.startswith("### "):
            h3 = line[4:].strip()
        m = CHECK_RE.match(line)
        if m:
            items.append(
                {
                    "id": m.group("id"),
                    "done": m.group("mark").lower() == "x",
                    "text": m.group("text").strip(),
                    "section": h2,
                    "subsection": h3,
                    "file": path.name,
                    "line": n,
                }
            )
    return items


def all_checklist_items() -> list[dict]:
    return parse_checklist(BENCHMARKS) + parse_checklist(GATHER)


def set_checkbox(item_id: str, done: bool = True, dry_run: bool = False) -> dict | None:
    """Toggle a checkbox in benchmarks.md or Gather List.md. Returns the item."""
    for path in (BENCHMARKS, GATHER):
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, line in enumerate(lines):
            m = CHECK_RE.match(line.rstrip("\n"))
            if m and m.group("id") == item_id:
                mark = "x" if done else " "
                new = f"{m.group('indent')}- [{mark}] (`{item_id}`) {m.group('text')}".rstrip()
                lines[i] = new + ("\n" if line.endswith("\n") else "")
                if not dry_run:
                    atomic_write(path, "".join(lines))
                return {"id": item_id, "file": path.name, "text": m.group("text").strip(), "done": done,
                        "was_done": m.group("mark").lower() == "x"}
    return None


def tech_nodes() -> list[dict]:
    return list(manifest().get("tech_tree") or [])


def techs_unlocked_by(source_id: str) -> list[str]:
    return [t["id"] for t in tech_nodes() if source_id in (t.get("unlocked_by") or [])]


def recompute_tech_effects(state: dict) -> dict:
    """Derive max bandwidth, cost multiplier, grid size, clock speed, sensors from unlocked tech."""
    nodes = {t["id"]: t for t in tech_nodes()}
    max_bw = 100
    cost = 1.0
    grid = 3
    clock = 1.0
    sensors: list[str] = []
    features: list[str] = []
    for tid in state.get("unlocked_tech", []):
        eff = (nodes.get(tid) or {}).get("effect") or {}
        if "max_bandwidth" in eff:
            max_bw += int(eff["max_bandwidth"])
        if "bandwidth_cost_mult" in eff:
            cost *= float(eff["bandwidth_cost_mult"])
        if "grid_size" in eff:
            grid = max(grid, int(eff["grid_size"]))
        if "clock_speed" in eff:
            clock *= float(eff["clock_speed"])
        if "sensor" in eff:
            sensors.append(eff["sensor"])
        if "feature" in eff:
            features.append(eff["feature"])
    state["max_bandwidth"] = max_bw
    clamp_bandwidth(state)
    return {"max_bandwidth": max_bw, "bandwidth_cost_mult": round(cost, 3), "grid_size": grid,
            "clock_speed": clock, "sensors": sensors, "features": features}


def award_source(state: dict, source_id: str) -> list[str]:
    """Unlock all tech nodes triggered by a benchmark/gather/challenge id."""
    new = []
    for tid in techs_unlocked_by(source_id):
        if tid not in state["unlocked_tech"]:
            state["unlocked_tech"].append(tid)
            new.append(tid)
    recompute_tech_effects(state)
    return new


def maybe_advance_stage(state: dict) -> int | None:
    done = set(state.get("completed_benchmarks", []))
    for item in all_checklist_items():
        if item["done"]:
            done.add(item["id"])
    stages = sorted(manifest().get("stages") or [], key=lambda s: int(s["stage"]))
    advanced = None
    for st in stages:
        n = int(st["stage"])
        if n != state["stage"]:
            continue
        req = st.get("benchmarks") or []
        if req and all(b in done for b in req) and any(int(s["stage"]) == n + 1 for s in stages):
            state["stage"] = n + 1
            advanced = n + 1
    return advanced


def stage_info(stage: int) -> dict:
    for st in manifest().get("stages") or []:
        if int(st["stage"]) == int(stage):
            return st
    return {"stage": stage, "name": f"Stage {stage}"}


def scheduled_block(when: dt.datetime | None = None) -> dict | None:
    when = when or now()
    sched = schedule()
    day = when.strftime("%A").lower()
    blocks = (sched.get("week") or {}).get(day) or []
    if not blocks:
        return None
    chosen = blocks[0]
    for b in blocks:
        h, m = (int(x) for x in str(b.get("start", "00:00")).split(":"))
        if (h, m) <= (when.hour, when.minute):
            chosen = b
    return {"day": day, **chosen, "all": blocks}


def track_config(track: str) -> dict:
    tracks = (schedule().get("tracks") or {})
    for k, v in tracks.items():
        if k.lower() == track.lower():
            return {"name": k, **(v or {})}
    return {"name": track.capitalize(), "stat": f"hours_{track.lower()}"}


# --------------------------------------------------------------------------
# Markdown helpers
# --------------------------------------------------------------------------

FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def read_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = _parse_fm(m.group(1))
    except Exception:
        fm = {}
    return fm, text[m.end():]


def _parse_fm(raw: str) -> dict:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(raw) or {}
    except ImportError:
        return _mini_yaml(raw) or {}


def set_frontmatter_field(path: Path, key: str, value: Any, dry_run: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value).lower() if isinstance(value, bool) else str(value)
    if not m:
        text = f"---\n{key}: {rendered}\n---\n" + text
    else:
        fm = m.group(1)
        if re.search(rf"^{re.escape(key)}:.*$", fm, re.M):
            fm = re.sub(rf"^{re.escape(key)}:.*$", f"{key}: {rendered}", fm, count=1, flags=re.M)
        else:
            fm = fm + f"\n{key}: {rendered}"
        text = f"---\n{fm}\n---\n" + text[m.end():]
    if not dry_run:
        atomic_write(path, text)


DAILY_FIELDS = ["hours", "track", "pages", "hours_coding", "hours_math", "hours_reading", "hours_writing", "hours_discussion"]


def daily_note_path(d: dt.date | None = None) -> Path:
    return TODAY_DIR / f"{(d or today()).isoformat()}.md"


def ensure_daily_note(dry_run: bool = False) -> tuple[Path, bool]:
    p = daily_note_path()
    if p.exists():
        return p, False
    d = today()
    body = (
        f"---\ntype: daily\ndate: {d.isoformat()}\n---\n\n# {d.strftime('%A, %B')} {d.day} {d.year}\n\n"
        "hours:: 0\ntrack:: \npages:: 0\nhours_coding:: 0\nhours_math:: 0\nhours_reading:: 0\n"
        "hours_writing:: 0\nhours_discussion:: 0\n\n## Sessions\n\n## Notes\n\n## One thing I noticed about myself today\n"
    )
    if not dry_run:
        atomic_write(p, body)
    return p, True


def get_inline_field(text: str, field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}::[ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def set_inline_field(text: str, field: str, value: Any) -> str:
    pat = re.compile(rf"^{re.escape(field)}::[ \t]*.*$", re.M)
    line = f"{field}:: {value}"
    if pat.search(text):
        return pat.sub(line, text, count=1)
    # insert after frontmatter + title
    parts = text.split("\n## ", 1)
    if len(parts) == 2:
        return parts[0].rstrip("\n") + f"\n{line}\n\n## " + parts[1]
    return text.rstrip("\n") + f"\n{line}\n"


def add_inline_number(text: str, field: str, amount: float) -> tuple[str, float]:
    cur = get_inline_field(text, field)
    try:
        val = float(cur) if cur else 0.0
    except ValueError:
        val = 0.0
    val = round(val + amount, 2)
    shown: Any = int(val) if float(val).is_integer() else val
    return set_inline_field(text, field, shown), val


def append_under_heading(text: str, heading: str, line: str) -> str:
    """Append `line` at the end of section `heading` (e.g. '## Sessions')."""
    lines = text.splitlines()
    level = heading.split(" ")[0]
    try:
        idx = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return text.rstrip("\n") + f"\n\n{heading}\n{line}\n"
    hl = len(level)
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        l = lines[j]
        k = len(l) - len(l.lstrip("#"))
        if k and k <= hl and l[k:k + 1] == " ":
            end = j
            break
    insert_at = end
    while insert_at > idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, line)
    if insert_at + 1 < len(lines) and lines[insert_at + 1].startswith("#"):
        lines.insert(insert_at + 1, "")
    return "\n".join(lines) + "\n"


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------
# Platform helpers (macOS first, Linux/Windows fallbacks)
# --------------------------------------------------------------------------

SYSTEM = platform.system()


def vault_name() -> str:
    return config().get("obsidian_vault_name") or ROOT.name or VAULT_NAME_DEFAULT


def obsidian_uri(rel_file: str) -> str:
    return "obsidian://open?" + urllib.parse.urlencode(
        {"vault": vault_name(), "file": rel_file}, quote_via=urllib.parse.quote
    )


def open_target(target: str) -> bool:
    """Open a URL or file with the OS handler. Returns True if a launcher was found."""
    if os.environ.get("PRAXIS_NO_OPEN"):
        return False
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif SYSTEM == "Windows":
            os.startfile(target)  # type: ignore[attr-defined]
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return False
        return True
    except Exception:
        return False


def open_in_obsidian(rel_file: str) -> bool:
    return open_target(obsidian_uri(rel_file))


def copy_to_clipboard(text: str) -> bool:
    cmds: list[list[str]] = []
    if SYSTEM == "Darwin":
        cmds.append(["pbcopy"])
    elif SYSTEM == "Windows":
        cmds.append(["clip"])
    else:
        cmds += [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for c in cmds:
        if shutil.which(c[0]):
            try:
                subprocess.run(c, input=text.encode("utf-8"), check=True, timeout=5)
                return True
            except Exception:
                continue
    return False


def python_exe() -> str:
    return sys.executable or "python3"


def run_git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    cfg = config()
    name, email = cfg.get("git_name"), cfg.get("git_email")
    if not name or not email:
        # Only fall back to a placeholder identity when git has none configured.
        have = subprocess.run(["git", "config", "user.email"], cwd=str(cwd), capture_output=True, text=True)
        if have.returncode != 0 or not have.stdout.strip():
            name, email = name or "Praxis Learner", email or "praxis@localhost"
    if name and email:
        for k, v in (("GIT_AUTHOR_NAME", name), ("GIT_AUTHOR_EMAIL", email),
                     ("GIT_COMMITTER_NAME", name), ("GIT_COMMITTER_EMAIL", email)):
            env.setdefault(k, v)
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check, env=env)


def git_available() -> bool:
    return shutil.which("git") is not None


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class PraxisError(Exception):
    pass


def emit(result: dict, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
        return
    msg = result.get("message")
    if msg:
        print(msg)
    for line in result.get("lines", []) or []:
        print(line)


def unique(seq: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Shared game actions (used by learn.py and drone_runner.py)
# --------------------------------------------------------------------------


def complete_item(state: dict, item_id: str, done: bool = True, dry_run: bool = False) -> dict:
    """Check (or uncheck) a benchmark / gather / credential and apply rewards."""
    item = set_checkbox(item_id, done, dry_run=dry_run)
    if item is None:
        raise PraxisError(f"No checklist item with id `{item_id}` in benchmarks.md or Gather List.md")
    new_tech: list[str] = []
    xp = 0
    if done:
        if item["file"] == BENCHMARKS.name:
            if item_id.startswith("cred_"):
                if item_id not in state["earned_credentials"]:
                    state["earned_credentials"].append(item_id)
            elif item_id not in state["completed_benchmarks"]:
                state["completed_benchmarks"].append(item_id)
        if not item["was_done"]:
            xp = int(rewards()["benchmark_xp"]) if item["file"] == BENCHMARKS.name else 50
            state["xp"] += xp
        new_tech = award_source(state, item_id)
    else:
        for key in ("completed_benchmarks", "earned_credentials"):
            if item_id in state[key]:
                state[key].remove(item_id)
    advanced = maybe_advance_stage(state) if done else None
    return {"item": item, "unlocked_tech": new_tech, "xp_awarded": xp, "stage_advanced_to": advanced}


def rebuild_portfolio(dry_run: bool = False) -> dict:
    """Run 10 Portfolio/build_resume.py in-process. Never raises."""
    if dry_run:
        return {"ok": True, "skipped": "dry-run"}
    script = PORTFOLIO / "build_resume.py"
    if not script.exists():
        return {"ok": False, "error": "10 Portfolio/build_resume.py missing"}
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("praxis_build_resume", script)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod.build(pdf=False)
    except Exception as e:  # pragma: no cover - reported, not fatal
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
