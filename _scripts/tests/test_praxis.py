"""End-to-end tests for the Praxis engine.

Each test runs the real CLI in a subprocess against a throwaway copy of the
vault (PRAXIS_ROOT), with a fake clock (PRAXIS_NOW) and a fake HOME so nothing
touches your real files.  Run:  python3 -m pytest _scripts/tests -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SOLUTIONS = Path(__file__).resolve().parent / "solutions"
NOW = "2026-11-09T19:30:00"  # a Monday


def _ignore(dirpath, names):
    skip = {".git", "__pycache__", ".pytest_cache", ".godot"}
    if Path(dirpath) == REPO / "code":
        skip |= {n for n in names if n != "drones"}
    if Path(dirpath) == REPO / "_curriculums":
        skip |= {n for n in names if n.startswith("_backup_")}
    if Path(dirpath) == REPO / "02 Today" or Path(dirpath) == REPO / "08 Cards":
        skip |= {n for n in names if n != ".gitkeep"}
    return skip & set(names)


@pytest.fixture()
def vault(tmp_path):
    root = tmp_path / "Learning"
    shutil.copytree(REPO, root, ignore=_ignore)
    # pristine state + starters regardless of the developer's own progress
    for f in (root / "_scripts" / "starters" / "drones").iterdir():
        shutil.copy2(f, root / "code" / "drones" / f.name)
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, PRAXIS_ROOT=str(root), PRAXIS_NOW=NOW, PRAXIS_NO_OPEN="1", HOME=str(home),
               SHELL="/bin/zsh", GIT_CONFIG_GLOBAL=str(home / ".gitconfig"))
    env.pop("ANTHROPIC_API_KEY", None)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    v = Vault(root, env, tmp_path)
    v.state_reset()
    v.run("python3", "_scripts/gen_assets.py")
    return v


class Vault:
    def __init__(self, root: Path, env: dict, tmp: Path):
        self.root, self.env, self.tmp = root, env, tmp

    def run(self, *cmd, check=True):
        r = subprocess.run(list(cmd), cwd=self.root, env=self.env, capture_output=True, text=True, timeout=120)
        if check and r.returncode not in (0, 1):
            raise AssertionError(r.stdout + r.stderr)
        return r

    def learn(self, *args, now: str | None = None) -> dict:
        env = dict(self.env)
        if now:
            env["PRAXIS_NOW"] = now
        r = subprocess.run([sys.executable, "_scripts/learn.py", *args, "--json"], cwd=self.root, env=env,
                           capture_output=True, text=True, timeout=120)
        assert r.stdout.strip(), r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    def state(self) -> dict:
        return json.loads((self.root / "_scripts/state.json").read_text())

    def write_state(self, s: dict) -> None:
        (self.root / "_scripts/state.json").write_text(json.dumps(s))

    def state_reset(self) -> None:
        base = {
            "curriculum_name": "Computational Social Science & AI", "stage": 1, "xp": 0,
            "cognitive_bandwidth": 100, "max_bandwidth": 100, "streak_days": 0, "last_active_date": None,
            "active_session": {"running": False, "track": None, "target_file": None, "start_timestamp": None},
            "current_focus": {"reading": "03 Reading/How to Read a Book.md", "course": "CS50x",
                              "essay": "04 Writing/Essay 01.md", "project": "07 Projects/csv-plotter.md"},
            "unlocked_tech": ["drone_move_basic", "grid_3x3"], "completed_benchmarks": [],
            "earned_credentials": [], "people_nodes": [],
            "weekly_stats": {"hours_math": 0.0, "hours_coding": 0.0, "hours_reading": 0.0, "hours_writing": 0.0,
                             "hours_discussion": 0.0, "pages_read": 0, "cards_due": 0, "cards_reviewed": 0},
        }
        self.write_state(base)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text()


# ----------------------------------------------------------------- core CLI

def test_status_json(vault):
    s = vault.learn("status")
    assert s["ok"] and s["state"]["stage"] == 1
    assert s["scheduled_block"]["track"] == "Coding"  # Monday
    assert {t["id"] for t in s["tech_tree"]} >= {"grid_5x5", "statistical_scanner"}
    assert len(s["benchmarks"]) == 18 + 16  # 18 stage benchmarks + 16 credentials
    assert any(c["id"] == "c3_graph" and c["locked"] for c in s["challenges"])


def test_start_stop_logs_hours_and_rewards(vault):
    r = vault.learn("start", "Math", now="2026-11-10T19:00:00")
    assert r["ok"] and r["session"]["track"] == "Math"
    assert vault.state()["active_session"]["running"]
    st = vault.state()
    st["cognitive_bandwidth"] = 10
    vault.write_state(st)
    r = vault.learn("stop", now="2026-11-10T20:30:00")
    assert r["ok"] and r["hours"] == 1.5 and r["xp_awarded"] == 90
    s = vault.state()
    assert s["weekly_stats"]["hours_math"] == 1.5
    assert s["cognitive_bandwidth"] == 55.0
    assert s["streak_days"] == 1 and not s["active_session"]["running"]
    note = vault.read("02 Today/2026-11-10.md")
    assert "hours:: 1.5" in note and "hours_math:: 1.5" in note and "track:: Math" in note
    assert "19:00–20:30 Math" in note
    assert (vault.root / "10 Portfolio/index.html").exists()


def test_streak_increments_on_consecutive_days(vault):
    vault.learn("pages", "10", now="2026-11-09T10:00:00")
    vault.learn("pages", "10", now="2026-11-10T10:00:00")
    assert vault.state()["streak_days"] == 2
    vault.learn("pages", "10", now="2026-11-13T10:00:00")
    assert vault.state()["streak_days"] == 1


def test_dry_run_writes_nothing(vault):
    before = vault.read("_scripts/state.json")
    for args in (["start", "Coding"], ["q", "x?"], ["pages", "5"], ["benchmark", "s1_stats"],
                 ["person", "Zed: likes chess"], ["project", "demo"], ["export-public", "--out", str(vault.tmp / "x")]):
        r = vault.learn(*args, "--dry-run")
        assert r["ok"], (args, r)
    assert vault.read("_scripts/state.json") == before
    assert "x?" not in vault.read("05 Questions.md")
    assert "[ ] (`s1_stats`)" in vault.read("01 Plan/benchmarks.md")
    assert not (vault.tmp / "x").exists()


def test_question_and_person(vault):
    vault.learn("q", "Why do weak ties matter?")
    assert "- [ ] 2026-11-09 — Why do weak ties matter? (from [[How to Read a Book]])" in vault.read("05 Questions.md")
    r = vault.learn("person", "Dana: training for a marathon")
    assert r["node"]["name"] == "Dana" and r["node"]["status"] == "active"
    vault.learn("person", "Dana: has a dog named Pixel")
    text = vault.read("06 People.md")
    assert text.count("## Dana") == 1 and "has a dog named Pixel" in text
    people = {p["name"]: p for p in vault.learn("status")["people"]}
    assert people["Dana"]["notes_count"] == 2
    import datetime as dt
    mentor = people["Example Mentor"]
    assert mentor["days_since"] == (dt.date(2026, 11, 9) - dt.date.fromisoformat(mentor["last_contact"])).days


def test_people_inbox_is_filed_on_sync(vault):
    p = vault.root / "06 People.md"
    p.write_text(p.read_text().replace("## Inbox\n", "## Inbox\n- 2026-11-01 — Riley: switching to a PhD in sociology\n"))
    vault.learn("sync")
    text = p.read_text()
    assert "## Riley\n- 2026-11-01 — switching to a PhD in sociology" in text
    inbox = text.split("## Inbox", 1)[1].split("## ", 1)[0]
    assert "Riley" not in inbox


def test_highlight_makes_cards_and_quiz_recharges(vault):
    st = vault.state()
    st["cognitive_bandwidth"] = 20
    vault.write_state(st)
    r = vault.learn("highlight", "Syntopical reading compares many books on one subject")
    assert r["ok"] and r["bandwidth_awarded"] == 10
    assert ">> Syntopical reading" in vault.read("03 Reading/How to Read a Book.md")
    r = vault.learn("card", "Granovetter 1973 :: The Strength of Weak Ties")
    q = vault.learn("quiz")
    assert len(q["questions"]) >= 3
    cid = q["questions"][0]["id"]
    a = vault.learn("quiz", "--answer", cid, "--correct")
    assert a["ok"] and a["bandwidth_awarded"] == 8
    cards = "".join(p.read_text() for p in (vault.root / "08 Cards").glob("*.md"))
    assert re.search(r"<!--SR:!2026-11-10,1,260-->", cards)
    # idempotent extraction
    n = len(cards)
    vault.run(sys.executable, "_scripts/make_cards.py")
    assert len("".join(p.read_text() for p in (vault.root / "08 Cards").glob("*.md"))) == n


def test_benchmark_unlocks_tech_and_updates_resume(vault):
    r = vault.learn("benchmark", "g_openintro")
    assert "statistical_scanner" in r["unlocked_tech"]
    assert "[x] (`g_openintro`)" in vault.read("01 Plan/Gather List.md")
    r = vault.learn("benchmark", "cred_cs50")
    assert "loop_coprocessor" in r["unlocked_tech"]
    s = vault.state()
    assert "cred_cs50" in s["earned_credentials"]
    resume = json.loads(vault.read("10 Portfolio/resume.json"))
    assert any("CS50" in c["name"] for c in resume["certificates"])
    eff = vault.learn("status")["effects"]
    assert eff["bandwidth_cost_mult"] == 0.8
    r = vault.learn("benchmark", "cred_cs50", "--undo")
    assert "cred_cs50" not in vault.state()["earned_credentials"]
    assert vault.learn("benchmark", "nope")["ok"] is False


def test_stage_advances_when_all_stage_benchmarks_done(vault):
    for b in ("s1_csv", "s1_stats", "s1_read", "s1_write"):
        vault.learn("benchmark", b)
    assert vault.state()["stage"] == 1
    r = vault.learn("benchmark", "s1_biases")
    assert r["stage_advanced_to"] == 2 and vault.state()["stage"] == 2
    assert vault.state()["max_bandwidth"] == 125  # Attention Capacitor I from s1_read


def test_project_creates_git_repo(vault):
    r = vault.learn("project", "Weak Ties Explorer", "--summary", "Network analysis")
    repo = vault.root / "code/weak-ties-explorer"
    assert r["ok"] and (repo / ".git").is_dir()
    for f in ("README.md", "main.py", "tests.py", ".gitignore"):
        assert (repo / f).exists()
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, env=vault.env, capture_output=True, text=True)
    assert "Initial commit" in log.stdout
    assert subprocess.run([sys.executable, "tests.py"], cwd=repo, capture_output=True).returncode == 0
    assert vault.state()["current_focus"]["project"] == "07 Projects/weak-ties-explorer.md"


def test_publish_and_critique_clipboard_fallback(vault):
    r = vault.learn("critique", "Essay 01", "--clipboard")
    assert r["ok"] and r["mode"] == "clipboard"
    assert "ESSAY:" in vault.read("_scripts/prompts/.last_prompt.md")
    r = vault.learn("publish", "04 Writing/Essay 01.md")
    assert r["status"] == "published"
    assert (vault.root / "10 Portfolio/essays/essay-01.html").exists()
    resume = json.loads(vault.read("10 Portfolio/resume.json"))
    assert resume["publications"][0]["name"] == "Essay 01"


def test_init_curriculum_round_trip(vault):
    r = vault.learn("init-curriculum", "fullstack_ai_engineer")
    assert r["ok"] and vault.state()["curriculum_name"] == "Full-Stack AI Engineer"
    s = vault.learn("status")
    assert any(b["id"] == "s2_rag" for b in s["benchmarks"])
    assert vault.learn("doctor")["errors"] == 0
    r = vault.learn("init-curriculum", "computational_social_science")
    assert vault.state()["curriculum_name"] == "Computational Social Science & AI"
    assert list((vault.root / "_curriculums").glob("_backup_*"))


def test_all_cartridges_are_consistent(vault):
    for t in ("blank_custom_template", "fullstack_ai_engineer", "computational_social_science"):
        vault.learn("init-curriculum", t)
        d = vault.learn("doctor")
        bad = [c for c in d["checks"] if c["level"] == "error"]
        assert not bad, (t, bad)


# ----------------------------------------------------------------- drones

def _drone(vault, script, challenge, *extra):
    return vault.learn("run-drone", script, challenge, *extra)


def test_c1_and_c2_starters_pass_and_commit(vault):
    r = _drone(vault, "c1_loops.py", "c1_loops")
    assert r["challenge_passed"], r["notes"]
    assert r["frames"][0]["action"] == "harvest_data" and r["frames"][0]["pos"] == [0, 0]
    assert "grid_5x5" in r["unlocked_tech"]
    assert r["git_commit"].startswith("Committed")
    assert vault.state()["cognitive_bandwidth"] == 51.0
    st = vault.state()
    st["cognitive_bandwidth"] = 100
    vault.write_state(st)
    r = _drone(vault, "c2_csv.py", "c2_csv")
    assert r["challenge_passed"], r["notes"]
    assert r["unlocked_benchmark"] == "s1_csv"
    assert (vault.root / "_assets/stage1_plot.png").exists()
    assert "[x] (`s1_csv`)" in vault.read("01 Plan/benchmarks.md")


def test_scaffolds_fail_reference_solutions_pass(vault):
    _drone(vault, "c1_loops.py", "c1_loops")  # unlocks grid_5x5
    for cid in ("c3_graph", "c4_numpy", "c5_schelling"):
        st = vault.state()
        st["cognitive_bandwidth"] = 100
        vault.write_state(st)
        bad = _drone(vault, f"{cid}.py", cid, "--dry-run")
        assert not bad["challenge_passed"], cid
        shutil.copy2(SOLUTIONS / f"{cid}.py", vault.root / "code/drones" / f"{cid}_solved.py")
        good = _drone(vault, f"{cid}_solved.py", cid)
        assert good["challenge_passed"], (cid, good["notes"], good.get("stderr"))
    s = vault.state()
    assert {"s2_numpy", "s3_abm"} <= set(s["completed_benchmarks"])


def test_locked_challenge_and_zero_bandwidth(vault):
    r = _drone(vault, "c3_graph.py", "c3_graph")
    assert r.get("locked") and not r["challenge_passed"]
    st = vault.state()
    st["cognitive_bandwidth"] = 0
    vault.write_state(st)
    r = _drone(vault, "c1_loops.py", "c1_loops")
    assert r.get("out_of_bandwidth")


def test_bandwidth_runs_out_mid_script(vault):
    st = vault.state()
    st["cognitive_bandwidth"] = 10
    vault.write_state(st)
    r = _drone(vault, "c1_loops.py", "c1_loops")
    assert not r["challenge_passed"]
    assert any(f["action"] == "out_of_bandwidth" for f in r["frames"])
    assert vault.state()["cognitive_bandwidth"] == 0


def test_timeout_and_crash_are_reported(vault):
    for name in ("infinite.py", "crash.py"):
        shutil.copy2(SOLUTIONS / name, vault.root / "code/drones" / name)
    env_backup = dict(vault.env)
    vault.env["PRAXIS_DRONE_TIMEOUT"] = "2"
    r = _drone(vault, "infinite.py", "c1_loops")
    vault.env = env_backup
    assert r["timed_out"] and not r["success"]
    r = _drone(vault, "crash.py", "c1_loops")
    assert not r["success"]
    err = [f for f in r["frames"] if f["action"] == "error"][0]
    assert "ValueError: boom" in err["log"] and "crash.py" in err["traceback"]


def test_world_preview(vault):
    r = vault.learn("world", "c3_graph")
    assert r["world"]["size"] == [7, 7] and "graph" in r["world"]["data"]
    assert "_hidden" not in vault.learn("world", "c4_numpy")["world"]


# ----------------------------------------------------------------- export & doctor

def test_export_public_is_sanitized(vault):
    secret = "Jordan " + "Secret" + "name"
    vault.learn("person", f"{secret}: told me about a private matter")
    (vault.root / "02 Today/2026-11-09.md").write_text("hours:: 2\nprivate diary entry\n")
    (vault.root / "09 Reviews/2026-W45.md").write_text("private review")
    (vault.root / "04 Writing/Draft Secret.md").write_text("---\nstatus: draft\n---\nunpublished thoughts")
    out = vault.tmp / "public"
    r = vault.learn("export-public", "--out", str(out))
    assert r["ok"], r.get("leaks")
    assert not list((out / "02 Today").glob("*.md")) and not list((out / "09 Reviews").glob("*.md"))
    assert not (out / "04 Writing/Draft Secret.md").exists()
    assert "Jordan" not in (out / "06 People.md").read_text()
    blob = "\n".join(p.read_text(errors="ignore") for p in out.rglob("*") if p.is_file() and "tests" not in p.parts)
    assert secret not in blob and "private diary" not in blob
    st = json.loads((out / "_scripts/state.json").read_text())
    assert st["xp"] == 0 and st["completed_benchmarks"] == []
    assert (out / "README.md").read_text().startswith("# Praxis: The Diegetic Learning OS & Automation Game")
    assert (out / "game/project.godot").exists() and (out / "code/drones/c1_loops.py").exists()
    # the export is itself a working vault
    env = dict(vault.env, PRAXIS_ROOT=str(out))
    d = subprocess.run([sys.executable, "_scripts/learn.py", "doctor", "--json"], cwd=out, env=env, capture_output=True, text=True)
    assert json.loads(d.stdout)["errors"] == 0, d.stdout


def test_export_blocks_on_leak(vault):
    name = "Quinn " + "Leak" + "well"
    vault.learn("person", f"{name}: secret")
    (vault.root / "_templates/daily.md").write_text(f"Note about {name}")
    r = vault.learn("export-public", "--out", str(vault.tmp / "pub2"))
    assert not r["ok"] and any(name in x for x in r["leaks"])


def test_export_refuses_vault_and_foreign_dirs(vault):
    assert not vault.learn("export-public", "--out", str(vault.root / "sub"))["ok"]
    foreign = vault.tmp / "foreign"
    foreign.mkdir()
    (foreign / "important.txt").write_text("keep me")
    assert not vault.learn("export-public", "--out", str(foreign))["ok"]
    assert (foreign / "important.txt").exists()


def test_doctor_passes(vault):
    d = vault.learn("doctor")
    assert d["errors"] == 0, [c for c in d["checks"] if c["level"] == "error"]


def test_installers_dry_run(vault):
    r = vault.learn("install-alias")
    assert r["ok"] and "praxis-learn-alias" in (Path(vault.env["HOME"]) / ".zshrc").read_text()
    r = vault.learn("install-alias")
    assert r["changed"] is False
    r = vault.learn("install-scheduler", "--platform", "macos", "--dry-run")
    assert "com.praxis.learn.nightly" in r["plist"] and "sync --headless" in r["plist"]


def test_portfolio_html(vault):
    vault.learn("benchmark", "cred_cs50")
    vault.run(sys.executable, "10 Portfolio/build_resume.py", "--no-pdf")
    html = vault.read("10 Portfolio/index.html")
    assert "Try the engine: download Praxis OS" in html
    assert "CS50x: Introduction to Computer Science" in html
    assert "CLEP Introductory Psychology" not in html  # unearned credentials are hidden
