#!/usr/bin/env python3
"""learn — the Praxis command line. One command, same state as the Godot game.

Every subcommand accepts --json (machine output for Godot's OS.execute),
--dry-run (compute and report, write nothing) and --headless (never open
Obsidian or a browser).

    learn                       start the block scheduled for right now
    learn start [track]         start a deep-work session (Coding/Math/Reading/Writing/Discussion)
    learn stop                  stop it: log hours, earn XP + Cognitive Bandwidth
    learn status                full JSON snapshot (what the game renders)
    learn q "question"          add to 05 Questions.md
    learn person "Name: detail" log an interaction in 06 People.md
    learn highlight "text"      add a >> highlight to the current reading + make a card
    learn card "front :: back"  same, as an explicit flashcard
    learn pages 25              log pages read today
    learn benchmark <id>        check off a benchmark / gather item (--undo to uncheck)
    learn run-drone <py> <id>   run a drone script against a challenge
    learn critique <essay>      harsh AI critique (API key) or copy prompt to clipboard
    learn quiz                  5 flashcard questions; answers recharge bandwidth
    learn publish <essay>       mark an essay published (shows on the portfolio)
    learn focus <key> <value>   set current reading/course/essay/project
    learn project "name"        new project note + real git repo in code/<name>/
    learn init-curriculum <t>   switch cartridge (--list to see templates)
    learn world <challenge>     preview a challenge grid (used by the game)
    learn resume [--open]       rebuild résumé, portfolio and PDF
    learn export-public         build the sanitized public praxis-engine export
    learn sync                  cards + portfolio + git commit (+ --push, --public)
    learn doctor                verify the whole system
    learn game                  launch the Godot game
    learn install-alias         add `alias learn=...` to ~/.zshrc
    learn install-scheduler     nightly sync via launchd (macOS) / cron (Linux)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import make_cards  # noqa: E402

DEFAULT_MODEL = os.environ.get("PRAXIS_MODEL", "claude-opus-5-5")

# ==========================================================================
# Sessions
# ==========================================================================


def _resolve_target(track: str, state: dict) -> str:
    cfg = C.track_config(track)
    if cfg.get("file"):
        return cfg["file"]
    focus_key = cfg.get("focus")
    if focus_key:
        val = state["current_focus"].get(focus_key)
        if val and (C.ROOT / val).exists():
            return val
    return C.rel(C.daily_note_path())


def cmd_start(a) -> dict:
    state = C.load_state()
    if state["active_session"]["running"]:
        s = state["active_session"]
        return {"ok": False, "already_running": True, "session": s,
                "message": f"A {s['track']} session is already running since {s['start_timestamp']}. `learn stop` first."}
    track = a.track
    block = C.scheduled_block()
    if not track:
        track = (block or {}).get("track") or "Reading"
    track = C.track_config(track)["name"]
    note, created = C.ensure_daily_note(a.dry_run)
    target = a.file or _resolve_target(track, state)
    state["active_session"] = {"running": True, "track": track, "target_file": target,
                               "start_timestamp": C.now().isoformat()}
    C.save_state(state, a.dry_run)
    opened = False
    if not a.headless and not a.dry_run:
        opened = C.open_in_obsidian(target)
    return {"ok": True, "session": state["active_session"], "scheduled_block": block,
            "daily_note": C.rel(note), "daily_note_created": created, "opened_in_obsidian": opened,
            "dry_run": a.dry_run,
            "message": f"▶ {track} session started → {target}" + (" (dry-run)" if a.dry_run else "")}


def cmd_stop(a) -> dict:
    state = C.load_state()
    s = state["active_session"]
    if not s["running"]:
        return {"ok": False, "message": "No session running. `learn start [track]` first."}
    start = dt.datetime.fromisoformat(s["start_timestamp"])
    end = C.now()
    minutes = max(0.0, (end - start).total_seconds() / 60)
    if a.minutes is not None:
        minutes = float(a.minutes)
    hours = round(minutes / 60, 2)
    track = s["track"]
    stat = C.track_config(track).get("stat") or f"hours_{track.lower()}"
    r = C.rewards()
    xp = int(round(minutes * float(r["xp_per_minute"])))
    bw = round(minutes * float(r["bandwidth_per_minute"]), 1)

    note, _ = C.ensure_daily_note(a.dry_run)
    text = note.read_text(encoding="utf-8") if note.exists() else ""
    text, total = C.add_inline_number(text, "hours", hours)
    text, _ = C.add_inline_number(text, stat, hours)
    tracks_today = [t.strip() for t in (C.get_inline_field(text, "track") or "").split(",") if t.strip()]
    if track not in tracks_today:
        tracks_today.append(track)
    text = C.set_inline_field(text, "track", ", ".join(tracks_today))
    text = C.append_under_heading(text, "## Sessions",
                                  f"- {start.strftime('%H:%M')}–{end.strftime('%H:%M')} {track} ({hours:.2f}h) → [[{Path(s['target_file'] or '').stem}]]")

    before_bw = state["cognitive_bandwidth"]
    state["weekly_stats"][stat] = round(state["weekly_stats"].get(stat, 0) + hours, 2)
    state["lifetime_stats"][stat] = round(state["lifetime_stats"].get(stat, 0) + hours, 2)
    state["xp"] += xp
    state["cognitive_bandwidth"] += bw
    C.clamp_bandwidth(state)
    C.touch_streak(state)
    C.log_day(state, "hours", hours)
    C.log_day(state, stat, hours)
    state["active_session"] = {"running": False, "track": None, "target_file": None, "start_timestamp": None}
    if not a.dry_run:
        C.atomic_write(note, text)
    C.save_state(state, a.dry_run)
    portfolio = C.rebuild_portfolio(a.dry_run)
    return {"ok": True, "track": track, "minutes": round(minutes, 1), "hours": hours, "hours_today": total,
            "xp_awarded": xp, "bandwidth_awarded": round(state["cognitive_bandwidth"] - before_bw, 1),
            "cognitive_bandwidth": state["cognitive_bandwidth"], "streak_days": state["streak_days"],
            "portfolio": portfolio, "dry_run": a.dry_run,
            "message": f"■ {track}: {minutes:.0f} min logged (+{xp} XP, +{bw:g} bandwidth). Streak {state['streak_days']}d."}


# ==========================================================================
# Capture
# ==========================================================================


def cmd_q(a) -> dict:
    state = C.load_state()
    reading = state["current_focus"].get("reading")
    src = f" (from [[{Path(reading).stem}]])" if reading else ""
    line = f"- [ ] {C.today_str()} — {a.question.strip()}{src}"
    if not a.dry_run:
        text = C.QUESTIONS.read_text(encoding="utf-8") if C.QUESTIONS.exists() else "# Questions\n\n"
        C.atomic_write(C.QUESTIONS, text.rstrip("\n") + "\n" + line + "\n")
        C.touch_streak(state)
        C.save_state(state)
    return {"ok": True, "line": line, "dry_run": a.dry_run, "message": f"? Added: {line}"}


PERSON_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2})\s+[—-]+\s+(.*)$")


def parse_people() -> list[dict]:
    people: list[dict] = []
    if not C.PEOPLE.exists():
        return people
    cur = None
    for line in C.PEOPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            cur = None if name.lower() == "inbox" else {"name": name, "entries": []}
            if cur:
                people.append(cur)
            continue
        m = PERSON_LINE.match(line)
        if cur and m:
            cur["entries"].append({"date": m.group(1), "detail": m.group(2).strip()})
    return people


def people_status(days: int) -> str:
    return "active" if days <= 14 else "cooling" if days < 30 else "dormant"


def sync_people_nodes(state: dict) -> list[dict]:
    t = C.today()
    nodes = []
    old = {n["name"]: n for n in state.get("people_nodes", [])}
    for p in parse_people():
        dates = [e["date"] for e in p["entries"]]
        last = max(dates) if dates else old.get(p["name"], {}).get("last_contact") or t.isoformat()
        days = (t - dt.date.fromisoformat(last)).days
        nodes.append({"name": p["name"], "last_contact": last, "days_since": days,
                      "notes_count": len(p["entries"]), "status": people_status(days),
                      "recent": [e["detail"] for e in p["entries"][-3:]]})
    state["people_nodes"] = nodes
    return nodes


def add_person_entry(text: str, name: str, detail: str, date: str) -> str:
    line = f"- {date} — {detail}"
    heading = f"## {name}"
    existing = next((l for l in text.splitlines() if l.strip().lower() == heading.lower()), None)
    if existing:
        return C.append_under_heading(text, existing.strip(), line)
    return text.rstrip("\n") + f"\n\n{heading}\n{line}\n"


def process_people_inbox(dry_run: bool = False) -> int:
    """File `- date — Name: detail` lines from ## Inbox under each person."""
    if not C.PEOPLE.exists():
        return 0
    lines = C.PEOPLE.read_text(encoding="utf-8").splitlines()
    try:
        i = next(k for k, l in enumerate(lines) if l.strip().lower() == "## inbox")
    except StopIteration:
        return 0
    j = i + 1
    moved = []
    keep = []
    while j < len(lines) and not lines[j].startswith("## "):
        m = PERSON_LINE.match(lines[j])
        if m and ":" in m.group(2):
            name, detail = m.group(2).split(":", 1)
            moved.append((m.group(1), name.strip(), detail.strip()))
        elif lines[j].strip():
            keep.append(lines[j])
        j += 1
    if not moved:
        return 0
    text = "\n".join(lines[: i + 1] + keep + [""] + lines[j:]) + "\n"
    for date, name, detail in moved:
        text = add_person_entry(text, name, detail, date)
    if not dry_run:
        C.atomic_write(C.PEOPLE, text)
    return len(moved)


def cmd_person(a) -> dict:
    if ":" not in a.entry:
        raise C.PraxisError('Use the form: learn person "Name: detail you learned"')
    name, detail = (s.strip() for s in a.entry.split(":", 1))
    if not name or not detail:
        raise C.PraxisError("Both a name and a detail are required.")
    state = C.load_state()
    text = C.PEOPLE.read_text(encoding="utf-8") if C.PEOPLE.exists() else "# People\n\n## Inbox\n"
    text = add_person_entry(text, name, detail, C.today_str())
    xp = int(C.rewards()["person_xp"])
    if not a.dry_run:
        C.atomic_write(C.PEOPLE, text)
    state["xp"] += xp
    C.touch_streak(state)
    nodes = sync_people_nodes(state) if not a.dry_run else state["people_nodes"]
    C.save_state(state, a.dry_run)
    node = next((n for n in nodes if n["name"].lower() == name.lower()), None)
    return {"ok": True, "name": name, "detail": detail, "xp_awarded": xp, "node": node, "dry_run": a.dry_run,
            "message": f"👤 {name}: logged \"{detail}\" (+{xp} social XP)"}


def _reading_note(a, state: dict) -> Path:
    target = getattr(a, "file", None) or state["current_focus"].get("reading")
    if not target:
        raise C.PraxisError("No current reading. `learn focus reading \"03 Reading/<Book>.md\"`.")
    p = C.ROOT / target
    if not p.exists():
        raise C.PraxisError(f"Reading note not found: {target}")
    return p


def _add_highlight(a, body: str) -> dict:
    state = C.load_state()
    note = _reading_note(a, state)
    text = note.read_text(encoding="utf-8")
    text = C.append_under_heading(text, "## Highlights", f">> {body.strip()}")
    if a.dry_run:
        return {"ok": True, "note": C.rel(note), "dry_run": True, "message": f"[dry-run] would add >> {body}"}
    C.atomic_write(note, text)
    cards = make_cards.run()
    state = C.load_state()
    before = state["cognitive_bandwidth"]
    state["cognitive_bandwidth"] += float(C.rewards()["highlight_bandwidth"])
    C.clamp_bandwidth(state)
    state["xp"] += 5
    state["weekly_stats"]["cards_due"] = cards["cards_due"]
    C.touch_streak(state)
    C.save_state(state)
    return {"ok": True, "note": C.rel(note), "cards_created": cards["created"],
            "bandwidth_awarded": round(state["cognitive_bandwidth"] - before, 1),
            "cognitive_bandwidth": state["cognitive_bandwidth"],
            "message": f">> Highlight saved to {note.stem}; {len(cards['created'])} card(s) made "
                       f"(+{state['cognitive_bandwidth'] - before:g} bandwidth)."}


def cmd_highlight(a) -> dict:
    return _add_highlight(a, a.text)


def cmd_card(a) -> dict:
    if "::" not in a.card:
        raise C.PraxisError('Use: learn card "front :: back"')
    return _add_highlight(a, a.card)


def cmd_pages(a) -> dict:
    n = int(a.pages)
    state = C.load_state()
    note, _ = C.ensure_daily_note(a.dry_run)
    text = note.read_text(encoding="utf-8") if note.exists() else ""
    text, total = C.add_inline_number(text, "pages", n)
    state["weekly_stats"]["pages_read"] += n
    state["lifetime_stats"]["pages_read"] = state["lifetime_stats"].get("pages_read", 0) + n
    state["xp"] += n
    C.log_day(state, "pages", n)
    C.touch_streak(state)
    if not a.dry_run:
        C.atomic_write(note, text)
    C.save_state(state, a.dry_run)
    return {"ok": True, "pages_today": total, "pages_week": state["weekly_stats"]["pages_read"],
            "dry_run": a.dry_run, "message": f"📖 +{n} pages ({int(total)} today, {state['weekly_stats']['pages_read']} this week)"}


def cmd_focus(a) -> dict:
    key = a.key.lower()
    if key not in ("reading", "course", "essay", "project"):
        raise C.PraxisError("focus key must be reading, course, essay or project")
    state = C.load_state()
    state["current_focus"][key] = a.value
    C.save_state(state, a.dry_run)
    return {"ok": True, "current_focus": state["current_focus"], "message": f"Focus {key} → {a.value}"}


# ==========================================================================
# Benchmarks
# ==========================================================================


def cmd_benchmark(a) -> dict:
    state = C.load_state()
    res = C.complete_item(state, a.id, not a.undo, dry_run=a.dry_run)
    C.save_state(state, a.dry_run)
    portfolio = C.rebuild_portfolio(a.dry_run)
    item = res["item"]
    verb = "Unchecked" if a.undo else ("Already checked" if item["was_done"] else "Checked")
    msg = f"✔ {verb} `{a.id}` — {item['text']}"
    if res["unlocked_tech"]:
        msg += f"\n  Tech unlocked: {', '.join(res['unlocked_tech'])}"
    if res["stage_advanced_to"]:
        msg += f"\n  ★ Stage {res['stage_advanced_to']} reached!"
    return {"ok": True, **res, "unlocked_tech_all": state["unlocked_tech"], "stage": state["stage"],
            "portfolio": portfolio, "dry_run": a.dry_run, "message": msg}


# ==========================================================================
# Drone
# ==========================================================================


def cmd_run_drone(a) -> dict:
    import drone_runner

    return drone_runner.run_drone(a.script, a.challenge, a.dry_run, not a.no_commit)


def cmd_world(a) -> dict:
    """Preview a challenge world (for the game grid) without running anything."""
    import drone_runner

    state = C.load_state()
    effects = C.recompute_tech_effects(state)
    world = drone_runner.build_world(a.challenge, effects, state)
    world.pop("_hidden", None)
    return {"ok": True, "challenge": a.challenge, "world": world, "effects": effects,
            "message": f"{a.challenge}: {world['size'][0]}x{world['size'][1]} grid, {len(world['tiles'])} tiles"}


def cmd_resume(a) -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location("praxis_build_resume", C.PORTFOLIO / "build_resume.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    if a.dry_run:
        return {"ok": True, "dry_run": True, "message": "[dry-run] would rebuild 10 Portfolio/"}
    res = mod.build(pdf=not a.no_pdf)
    res["index_url"] = (C.PORTFOLIO / "index.html").as_uri()
    if a.open and not a.headless:
        res["opened"] = C.open_target(res["index_url"])
    return res


# ==========================================================================
# AI: critique & quiz
# ==========================================================================


def call_claude(prompt: str, system: str | None = None, max_tokens: int = 2500) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise C.PraxisError("ANTHROPIC_API_KEY not set")
    body = {"model": C.config().get("model", DEFAULT_MODEL), "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    try:
        import requests  # type: ignore

        r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=headers, timeout=180)
        if r.status_code >= 400:
            raise C.PraxisError(f"Anthropic API error {r.status_code}: {r.text[:300]}")
        data = r.json()
    except ImportError:
        import urllib.request

        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def _prompt(name: str) -> str:
    p = C.SCRIPTS / "prompts" / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve_note(arg: str, folder: Path) -> Path:
    p = Path(arg)
    for cand in (C.ROOT / arg, folder / arg, folder / f"{arg}.md", p):
        if cand.exists() and cand.is_file():
            return cand.resolve()
    raise C.PraxisError(f"Not found: {arg}")


def cmd_critique(a) -> dict:
    essay = _resolve_note(a.essay, C.WRITING)
    text = essay.read_text(encoding="utf-8")
    fm, body = C.read_frontmatter(essay)
    body = body.split("\n## Critique", 1)[0]
    prompt = _prompt("critique").replace("{{ESSAY}}", body.strip()).replace("{{TITLE}}", str(fm.get("title", essay.stem)))
    words = len(re.findall(r"\b\w+\b", body))
    if a.dry_run:
        return {"ok": True, "mode": "dry-run", "words": words, "prompt_chars": len(prompt),
                "message": f"[dry-run] would critique {essay.name} ({words} words)"}
    if os.environ.get("ANTHROPIC_API_KEY") and not a.clipboard:
        reply = call_claude(prompt)
        stamp = C.now().strftime("%Y-%m-%d %H:%M")
        new = text.rstrip("\n") + f"\n\n## Critique\n\n*{stamp} — {DEFAULT_MODEL}*\n\n{reply}\n"
        C.atomic_write(essay, new)
        C.set_frontmatter_field(essay, "words", words)
        return {"ok": True, "mode": "api", "critique": reply, "words": words,
                "message": f"Critique appended to {essay.name} under ## Critique."}
    copied = C.copy_to_clipboard(prompt)
    out = C.SCRIPTS / "prompts" / ".last_prompt.md"
    C.atomic_write(out, prompt)
    return {"ok": True, "mode": "clipboard", "copied": copied, "prompt_file": C.rel(out), "words": words,
            "message": ("Prompt + essay copied to clipboard" if copied else f"No clipboard tool; prompt saved to {C.rel(out)}")
                       + " — paste into Claude, then paste the reply under ## Critique."}


def cmd_quiz(a) -> dict:
    if a.answer:
        res = make_cards.review_card(a.answer, a.correct, a.dry_run)
        if res is None:
            raise C.PraxisError(f"No card with id {a.answer}")
        state = C.load_state()
        before = state["cognitive_bandwidth"]
        if a.correct:
            state["cognitive_bandwidth"] += float(C.rewards()["quiz_correct_bandwidth"])
            C.clamp_bandwidth(state)
            state["xp"] += 3
        state["weekly_stats"]["cards_reviewed"] += 1
        state["lifetime_stats"]["cards_reviewed"] = state["lifetime_stats"].get("cards_reviewed", 0) + 1
        state["weekly_stats"]["cards_due"] = make_cards.count_due() if not a.dry_run else state["weekly_stats"]["cards_due"]
        C.touch_streak(state)
        C.save_state(state, a.dry_run)
        gain = round(state["cognitive_bandwidth"] - before, 1)
        return {"ok": True, "review": res, "correct": a.correct, "bandwidth_awarded": gain,
                "cognitive_bandwidth": state["cognitive_bandwidth"],
                "message": f"{'✓' if a.correct else '✗'} next review {res['due']} (+{gain:g} bandwidth)"}
    if a.ai:
        state = C.load_state()
        note = _reading_note(a, state)
        prompt = _prompt("quiz").replace("{{NOTE}}", note.read_text(encoding="utf-8"))
        if os.environ.get("ANTHROPIC_API_KEY") and not a.dry_run:
            return {"ok": True, "mode": "api", "questions_text": call_claude(prompt), "message": "AI oral quiz ready."}
        copied = C.copy_to_clipboard(prompt) if not a.dry_run else False
        return {"ok": True, "mode": "clipboard", "copied": copied, "message": "Quiz prompt copied to clipboard."}

    cards = make_cards.load_cards()
    if not cards:
        make_cards.run(a.dry_run)
        cards = make_cards.load_cards()
    due = [c for c in cards if c["is_due"]]
    rest = [c for c in cards if not c["is_due"]]
    rng = random.Random(C.today_str())
    rng.shuffle(due)
    rng.shuffle(rest)
    picked = (due + rest)[: a.count]
    questions = [{"id": c["id"], "front": c["front"], "back": c["back"], "file": c["file"], "due": c["is_due"]} for c in picked]
    result = {"ok": True, "questions": questions, "cards_total": len(cards), "cards_due": len(due),
              "message": f"{len(questions)} question(s) — {len(due)} due of {len(cards)} cards."}
    if not a.json and sys.stdin.isatty() and questions and not a.dry_run:
        right = 0
        for i, q in enumerate(questions, 1):
            print(f"\nQ{i}. {q['front']}")
            input("   (Enter to reveal) ")
            print(f"   → {q['back']}")
            ok = input("   Got it? [y/N] ").strip().lower().startswith("y")
            right += ok
            ns = argparse.Namespace(answer=q["id"], correct=ok, dry_run=False, ai=False, json=False)
            print("   " + cmd_quiz(ns)["message"])
        result["message"] = f"Quiz done: {right}/{len(questions)} correct."
    return result


# ==========================================================================
# Writing & projects
# ==========================================================================


def cmd_publish(a) -> dict:
    essay = _resolve_note(a.essay, C.WRITING)
    fm, body = C.read_frontmatter(essay)
    words = len(re.findall(r"\b\w+\b", body.split("\n## Critique", 1)[0]))
    status = "draft" if a.undo else "published"
    if not a.dry_run:
        C.set_frontmatter_field(essay, "status", status)
        C.set_frontmatter_field(essay, "words", words)
        if not a.undo:
            C.set_frontmatter_field(essay, "published", C.today_str())
    state = C.load_state()
    if not a.undo and fm.get("status") != "published":
        state["xp"] += 100
    C.save_state(state, a.dry_run)
    portfolio = C.rebuild_portfolio(a.dry_run)
    return {"ok": True, "essay": C.rel(essay), "status": status, "words": words, "portfolio": portfolio,
            "message": f"📡 {essay.stem} → {status} ({words} words). Portfolio rebuilt."}


PROJECT_README = """# {name}

{summary}

Part of my [Praxis](../../SETUP_NOTES.md) learning portfolio.

## Run

```bash
python3 main.py
python3 -m pytest tests.py   # or: python3 tests.py
```
"""

PROJECT_MAIN = '''"""{name} — entry point."""


def main() -> None:
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
'''

PROJECT_TESTS = '''import unittest

import main


class SmokeTest(unittest.TestCase):
    def test_main_runs(self):
        main.main()


if __name__ == "__main__":
    unittest.main()
'''

PROJECT_GITIGNORE = "__pycache__/\n*.pyc\n.venv/\n.ipynb_checkpoints/\n.DS_Store\n*.egg-info/\n"


def cmd_project(a) -> dict:
    name = a.name.strip()
    slug = C.slugify(name)
    note = C.PROJECTS / f"{slug}.md"
    repo = C.CODE / slug
    created = []
    if a.dry_run:
        return {"ok": True, "note": C.rel(note), "repo": C.rel(repo), "dry_run": True,
                "message": f"[dry-run] would create {C.rel(note)} and git repo {C.rel(repo)}"}
    if not note.exists():
        C.atomic_write(note, (
            f"---\ntype: project\ntitle: {name}\nstatus: active\nstage: {C.load_state()['stage']}\n"
            f"repo: code/{slug}\ngithub: \"\"\nplot: \"\"\npublic: true\nskills: []\nsummary: \"{a.summary or ''}\"\n"
            f"started: {C.today_str()}\ntags: [project]\n---\n\n# {name}\n\nRepo: `code/{slug}/`\n\n## Goal\n\n## Log\n- {C.today_str()} — Project created.\n\n"
            "## Write-up (methods · results · limits)\n"))
        created.append(C.rel(note))
    repo.mkdir(parents=True, exist_ok=True)
    files = {"README.md": PROJECT_README.format(name=name, summary=a.summary or "A Praxis project."),
             "main.py": PROJECT_MAIN.format(name=name), "tests.py": PROJECT_TESTS, ".gitignore": PROJECT_GITIGNORE}
    for fname, content in files.items():
        p = repo / fname
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            created.append(C.rel(p))
    git = "git not installed"
    if C.git_available():
        if not (repo / ".git").exists():
            C.run_git(["init", "-q", "-b", "main"], repo)
        C.run_git(["add", "-A"], repo)
        res = C.run_git(["commit", "-q", "-m", f"Initial commit: {name}"], repo)
        git = "initialized + committed" if res.returncode == 0 else "initialized (nothing new to commit)"
    state = C.load_state()
    state["current_focus"]["project"] = C.rel(note)
    state["xp"] += 50
    C.save_state(state)
    portfolio = C.rebuild_portfolio()
    return {"ok": True, "note": C.rel(note), "repo": C.rel(repo), "created": created, "git": git,
            "portfolio": portfolio, "message": f"🛠 Project {name}: {C.rel(note)} + {C.rel(repo)}/ ({git})"}


# ==========================================================================
# Curriculum cartridges
# ==========================================================================

CART_FILES = ["Learning Path.md", "Gather List.md", "benchmarks.md", "curriculum_manifest.yaml"]


def list_templates() -> list[dict]:
    out = []
    if C.CURRICULUMS.exists():
        for d in sorted(C.CURRICULUMS.iterdir()):
            if d.is_dir() and not d.name.startswith(("_", ".")):
                man = d / "curriculum_manifest.yaml"
                name = (C.load_yaml(man) or {}).get("name", d.name) if man.exists() else d.name
                out.append({"id": d.name, "name": name, "complete": all((d / f).exists() for f in CART_FILES)})
    return out


def cmd_init_curriculum(a) -> dict:
    if a.list or not a.template:
        t = list_templates()
        return {"ok": True, "templates": t, "message": "Templates:\n" + "\n".join(f"  {x['id']:<34} {x['name']}" for x in t)}
    if a.generate:
        return generate_curriculum(a)
    src = C.CURRICULUMS / a.template
    if not src.is_dir():
        raise C.PraxisError(f"No template {a.template!r}. Try: learn init-curriculum --list")
    missing = [f for f in CART_FILES if not (src / f).exists()]
    if missing:
        raise C.PraxisError(f"Template {a.template} is missing {', '.join(missing)}")
    stamp = C.now().strftime("%Y%m%d-%H%M%S")
    backup = C.CURRICULUMS / f"_backup_{stamp}"
    n = 1
    while backup.exists():
        n += 1
        backup = C.CURRICULUMS / f"_backup_{stamp}-{n}"
    if a.dry_run:
        return {"ok": True, "dry_run": True, "message": f"[dry-run] would back up 01 Plan/ to {C.rel(backup)} and install {a.template}"}
    backup.mkdir(parents=True)
    for f in CART_FILES + ["state.md"]:
        if (C.PLAN / f).exists():
            shutil.copy2(C.PLAN / f, backup / f)
    for f in CART_FILES:
        shutil.copy2(src / f, C.PLAN / f)
    man = C.manifest()
    state = C.load_state()
    state["curriculum_name"] = man.get("name", a.template)
    state["stage"] = 1
    state["completed_benchmarks"] = []
    state["earned_credentials"] = []
    base = [t["id"] for t in man.get("tech_tree") or [] if not t.get("unlocked_by")]
    state["unlocked_tech"] = base or ["drone_move_basic", "grid_3x3"]
    # Re-apply anything already checked in the new cartridge
    for item in C.all_checklist_items():
        if item["done"]:
            C.award_source(state, item["id"])
            key = "earned_credentials" if item["id"].startswith("cred_") else "completed_benchmarks"
            if item["file"] == C.BENCHMARKS.name:
                state[key].append(item["id"])
    C.recompute_tech_effects(state)
    C.save_state(state)
    portfolio = C.rebuild_portfolio()
    return {"ok": True, "installed": a.template, "backup": C.rel(backup), "curriculum_name": state["curriculum_name"],
            "portfolio": portfolio, "message": f"Cartridge '{state['curriculum_name']}' installed. Old plan backed up to {C.rel(backup)}."}


def generate_curriculum(a) -> dict:
    goal = a.generate
    prompt = _prompt("generate_curriculum").replace("{{GOAL}}", goal)
    slug = C.slugify(a.template)
    dest = C.CURRICULUMS / slug
    if a.dry_run:
        return {"ok": True, "dry_run": True, "message": f"[dry-run] would generate {C.rel(dest)} for: {goal}"}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        copied = C.copy_to_clipboard(prompt)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "PROMPT.md").write_text(prompt, encoding="utf-8")
        return {"ok": True, "mode": "clipboard", "copied": copied, "folder": C.rel(dest),
                "message": f"Prompt {'copied to clipboard' if copied else 'saved'} ({C.rel(dest)}/PROMPT.md). Paste the 4 files the model returns into {C.rel(dest)}/, then run `learn init-curriculum {slug}`."}
    reply = call_claude(prompt, max_tokens=16000)
    files = dict(re.findall(r"=== FILE: (.+?) ===\n(.*?)(?=\n=== FILE: |\n=== END ===|\Z)", reply, re.S))
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for fname, content in files.items():
        fname = fname.strip()
        if fname in CART_FILES:
            (dest / fname).write_text(content.strip() + "\n", encoding="utf-8")
            written.append(fname)
    (dest / "README.md").write_text(f"# {goal}\n\nGenerated by `learn init-curriculum {slug} --generate`.\n", encoding="utf-8")
    missing = [f for f in CART_FILES if f not in written]
    return {"ok": not missing, "mode": "api", "folder": C.rel(dest), "written": written, "missing": missing,
            "message": f"Generated {len(written)}/4 files in {C.rel(dest)}." + (f" Missing: {missing}" if missing else f" Install with `learn init-curriculum {slug}`.")}


# ==========================================================================
# Export, sync
# ==========================================================================


def cmd_export_public(a) -> dict:
    import export_public

    out = Path(a.out).expanduser() if a.out else None
    return export_public.run(out, dry_run=a.dry_run, force=a.force)


def cmd_sync(a) -> dict:
    steps = {}
    steps["cards"] = make_cards.run(a.dry_run)
    steps["people_inbox_filed"] = process_people_inbox(a.dry_run)
    state = C.load_state()
    sync_people_nodes(state)
    C.save_state(state, a.dry_run)
    steps["portfolio"] = C.rebuild_portfolio(a.dry_run)
    steps["vault_git"] = _git_commit_all(C.ROOT, f"praxis sync {C.now().isoformat(timespec='minutes')}", a.dry_run, a.push)
    if a.public:
        import export_public

        out = Path(a.out).expanduser() if a.out else None
        exp = export_public.run(out, dry_run=a.dry_run)
        steps["export"] = {k: exp[k] for k in ("ok", "out", "files", "message") if k in exp}
        if exp.get("ok") and (Path(exp["out"]) / ".git").exists():
            steps["public_git"] = _git_commit_all(Path(exp["out"]), "Update Praxis engine & portfolio", a.dry_run, a.push)
    return {"ok": True, "steps": steps, "dry_run": a.dry_run,
            "message": f"Synced: {len(steps['cards']['created'])} new cards, {steps['people_inbox_filed']} inbox people filed, git: {steps['vault_git']}"}


def _git_commit_all(repo: Path, msg: str, dry_run: bool, push: bool) -> str:
    if not C.git_available():
        return "git not installed"
    if C.run_git(["rev-parse", "--is-inside-work-tree"], repo).returncode != 0:
        return "not a git repo (run `git init` — see SETUP_NOTES.md)"
    if dry_run:
        changed = C.run_git(["status", "--porcelain"], repo).stdout.strip().splitlines()
        return f"[dry-run] {len(changed)} changed path(s)"
    C.run_git(["add", "-A"], repo)
    res = C.run_git(["commit", "-q", "-m", msg], repo)
    out = "committed" if res.returncode == 0 else "nothing to commit"
    if push:
        if C.run_git(["remote"], repo).stdout.strip():
            p = C.run_git(["push", "-q"], repo)
            out += ", pushed" if p.returncode == 0 else f", push failed: {p.stderr.strip()[-200:]}"
        else:
            out += ", no remote configured"
    return out


# ==========================================================================
# Status (the game's data feed)
# ==========================================================================


def essays() -> list[dict]:
    out = []
    if C.WRITING.exists():
        for p in sorted(C.WRITING.glob("*.md")):
            fm, body = C.read_frontmatter(p)
            words = len(re.findall(r"\b\w+\b", body.split("\n## Critique", 1)[0]))
            out.append({"path": C.rel(p), "title": str(fm.get("title") or p.stem), "status": fm.get("status", "draft"),
                        "due": str(fm.get("due") or ""), "words": words, "has_critique": "\n## Critique" in body})
    return out


def drone_files() -> list[str]:
    return sorted(p.name for p in C.DRONES.glob("*.py")) if C.DRONES.exists() else []


def build_status() -> dict:
    state = C.load_state()
    effects = C.recompute_tech_effects(state)
    sync_people_nodes(state)
    man = C.manifest()
    items = C.all_checklist_items()
    done_ids = {i["id"] for i in items if i["done"]} | set(state["lifetime_stats"].get("challenges_passed", []))
    item_text = {i["id"]: i["text"] for i in items}
    tech = []
    for t in man.get("tech_tree") or []:
        tech.append({**t, "unlocked": t["id"] in state["unlocked_tech"],
                     "sources": [{"id": s, "text": item_text.get(s, f"Pass drone challenge {s}"), "done": s in done_ids}
                                 for s in t.get("unlocked_by") or []]})
    challenges = []
    for c in man.get("challenges") or []:
        req = c.get("requires_tech") or []
        challenges.append({**c, "locked": any(r not in state["unlocked_tech"] for r in req),
                           "passed": c["id"] in state["lifetime_stats"].get("challenges_passed", [])})
    tracks = []
    for t in man.get("tracks") or []:
        ids = t.get("items") or []
        d = sum(1 for i in ids if i in done_ids)
        tracks.append({"id": t["id"], "label": t["label"], "color": t.get("color", "#39d98a"), "done": d,
                       "total": len(ids), "pct": round(100 * d / len(ids)) if ids else 0,
                       "hours_week": state["weekly_stats"].get(t.get("hours_key", ""), 0),
                       "hours_lifetime": state["lifetime_stats"].get(t.get("hours_key", ""), 0)})
    note = C.daily_note_path()
    today_fields = {}
    if note.exists():
        txt = note.read_text(encoding="utf-8")
        today_fields = {f: C.get_inline_field(txt, f) for f in C.DAILY_FIELDS}
    sched = C.schedule()
    st = C.stage_info(state["stage"])
    q_open = 0
    if C.QUESTIONS.exists():
        q_open = len(re.findall(r"^- \[ \]", C.QUESTIONS.read_text(encoding="utf-8"), re.M))
    lifetime_hours = round(sum(v for k, v in state["lifetime_stats"].items() if k.startswith("hours_")), 2)
    return {
        "ok": True,
        "vault_root": str(C.ROOT),
        "today": C.today_str(),
        "now": C.now().isoformat(),
        "state": state,
        "effects": effects,
        "stage": {"number": state["stage"], "name": st.get("name"), "months": st.get("months"),
                  "people_habit": st.get("people_habit", ""), "plateau_warning": st.get("plateau_warning", ""),
                  "hours_target": (sched.get("stage_hour_targets") or {}).get(state["stage"], st.get("hours_target", 0)),
                  "benchmarks": st.get("benchmarks", [])},
        "lifetime_hours": lifetime_hours,
        "scheduled_block": C.scheduled_block(),
        "week_schedule": sched.get("week", {}),
        "weekly_floor_hours": sched.get("weekly_floor_hours"),
        "benchmarks": [i for i in items if i["file"] == C.BENCHMARKS.name],
        "gather": [i for i in items if i["file"] == C.GATHER.name],
        "tech_tree": tech,
        "challenges": challenges,
        "tracks": tracks,
        "essays": essays(),
        "drone_files": drone_files(),
        "people": state["people_nodes"],
        "cards_due": make_cards.count_due(),
        "today_note": {"path": C.rel(note), "exists": note.exists(), **today_fields},
        "open_questions": q_open,
        "templates": list_templates(),
        "api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


def cmd_status(a) -> dict:
    s = build_status()
    if a.json:
        return s
    st = s["state"]
    blk = s["scheduled_block"]
    lines = [
        f"Praxis — {st['curriculum_name']}",
        f"  Stage {st['stage']} ({s['stage']['name']}) · {st['xp']} XP · 🔥 {st['streak_days']}d streak",
        f"  Bandwidth {st['cognitive_bandwidth']}/{st['max_bandwidth']} · cards due {s['cards_due']} · open questions {s['open_questions']}",
        f"  Today's block: {blk['track']} @ {blk['start']} ({blk['hours']}h)" if blk else "  No block scheduled today",
        f"  Session: {'running ' + st['active_session']['track'] if st['active_session']['running'] else 'idle'}",
        "  Tracks: " + " · ".join(f"{t['label']} {t['pct']}%" for t in s["tracks"]),
    ]
    return {"ok": True, "message": "\n".join(lines)}


# ==========================================================================
# Doctor
# ==========================================================================


def find_godot() -> str | None:
    cands = [os.environ.get("GODOT_BIN"), C.config().get("godot_bin"), shutil.which("godot"), shutil.which("godot4"),
             "/Applications/Godot.app/Contents/MacOS/Godot", "/Applications/Godot_mono.app/Contents/MacOS/Godot",
             str(Path.home() / "Applications/Godot.app/Contents/MacOS/Godot")]
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def cmd_doctor(a) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "", level: str = "error") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "level": "ok" if ok else level})

    v = sys.version_info
    add("python >= 3.11", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro}")
    for d in ["01 Plan", "02 Today", "03 Reading", "04 Writing", "07 Projects", "08 Cards", "09 Reviews",
              "10 Portfolio", "_curriculums", "_templates", "_scripts", "_scripts/prompts", "_assets", "code/drones",
              "game", ".obsidian"]:
        add(f"dir {d}/", (C.ROOT / d).is_dir())
    for f in ["00 Dashboard.md", "05 Questions.md", "06 People.md", "SETUP_NOTES.md", "01 Plan/state.md",
              "_scripts/schedule.yaml", "_scripts/requirements.txt", "_scripts/prompts/critique.md",
              "_scripts/prompts/quiz.md", "_scripts/prompts/generate_curriculum.md", "10 Portfolio/build_resume.py",
              "_scripts/export_public.py", "_scripts/station_api.py", "_scripts/drone_runner.py",
              "_scripts/make_cards.py"] + [f"01 Plan/{x}" for x in CART_FILES]:
        add(f"file {f}", (C.ROOT / f).is_file())
    for mod, lvl in [("yaml", "error"), ("requests", "warn"), ("numpy", "warn"), ("pandas", "warn"),
                     ("matplotlib", "warn"), ("readability", "warn")]:
        try:
            __import__(mod)
            add(f"python module {mod}", True)
        except ImportError:
            add(f"python module {mod}", False, "pip3 install -r _scripts/requirements.txt", lvl)
    # state
    try:
        raw = json.loads(C.STATE_FILE.read_text(encoding="utf-8"))
        miss = [k for k in ("stage", "xp", "cognitive_bandwidth", "active_session", "current_focus", "weekly_stats",
                            "unlocked_tech", "completed_benchmarks", "people_nodes") if k not in raw]
        add("state.json schema", not miss, f"missing {miss}" if miss else "valid")
    except Exception as e:
        add("state.json schema", False, str(e))
    # manifest consistency
    try:
        man = C.manifest()
        ids = {i["id"] for i in C.all_checklist_items()}
        chall = {c["id"] for c in man.get("challenges") or []}
        refs = set()
        for t in man.get("tech_tree") or []:
            refs |= set(t.get("unlocked_by") or [])
        for t in man.get("tracks") or []:
            refs |= set(t.get("items") or [])
        for st in man.get("stages") or []:
            refs |= set(st.get("benchmarks") or [])
        for c in man.get("challenges") or []:
            if c.get("benchmark"):
                refs.add(c["benchmark"])
        dangling = sorted(refs - ids - chall)
        add("manifest ↔ checklists", not dangling, f"unknown ids: {dangling}" if dangling else f"{len(ids)} checklist ids")
        tech_ids = {t["id"] for t in man.get("tech_tree") or []}
        bad_req = sorted({r for c in man.get("challenges") or [] for r in c.get("requires_tech") or []} - tech_ids)
        add("challenge tech gates", not bad_req, f"unknown tech {bad_req}" if bad_req else "ok")
        missing_starters = [c["starter"] for c in man.get("challenges") or [] if c.get("starter") and not (C.DRONES / c["starter"]).exists()]
        add("drone starter scripts", not missing_starters, f"missing {missing_starters}" if missing_starters else "ok", "warn")
    except Exception as e:
        add("curriculum_manifest.yaml", False, str(e))
    # schedule
    try:
        sched = C.schedule()
        tracks = set((sched.get("tracks") or {}).keys())
        used = {b["track"] for blocks in (sched.get("week") or {}).values() for b in blocks or []}
        add("schedule.yaml tracks", used <= tracks, f"undefined: {sorted(used - tracks)}" if used - tracks else "ok")
    except Exception as e:
        add("schedule.yaml", False, str(e))
    # obsidian
    for f in ["app.json", "community-plugins.json", "hotkeys.json", "core-plugins.json", "daily-notes.json"]:
        p = C.ROOT / ".obsidian" / f
        try:
            json.loads(p.read_text(encoding="utf-8"))
            add(f"obsidian {f}", True)
        except Exception as e:
            add(f"obsidian {f}", False, str(e))
    try:
        hk = json.loads((C.ROOT / ".obsidian/hotkeys.json").read_text(encoding="utf-8"))
        add("obsidian hotkeys (5)", len(hk) >= 5, f"{len(hk)} bound")
    except Exception:
        pass
    # game
    pg = C.GAME / "project.godot"
    add("godot project.godot", pg.exists())
    if pg.exists():
        txt = pg.read_text(encoding="utf-8")
        add("godot config_version=5 (Godot 4)", "config_version=5" in txt)
        main_scene = re.search(r'run/main_scene="res://(.+?)"', txt)
        add("godot main scene exists", bool(main_scene and (C.GAME / main_scene.group(1)).exists()),
            main_scene.group(1) if main_scene else "not set")
        for m in re.finditer(r'="\*?res://(.+?)"', txt):
            add(f"godot res://{m.group(1)}", (C.GAME / m.group(1)).exists())
    for scn in C.GAME.glob("scenes/*.tscn") if C.GAME.exists() else []:
        for m in re.finditer(r'path="res://(.+?)"', scn.read_text(encoding="utf-8")):
            add(f"{scn.name} → {m.group(1)}", (C.GAME / m.group(1)).exists())
    g = find_godot()
    add("godot binary", bool(g), g or "brew install --cask godot (or set GODOT_BIN)", "warn")
    # tools
    add("git", C.git_available(), shutil.which("git") or "install git")
    add("vault is a git repo", (C.ROOT / ".git").exists(), "git init (see SETUP_NOTES.md)", "warn")
    pdf = next((t for t in ("typst", "weasyprint", "wkhtmltopdf", "pandoc") if shutil.which(t)), None)
    add("PDF tool (typst/weasyprint/wkhtmltopdf/pandoc)", bool(pdf), pdf or "brew install typst", "warn")
    add("survey dataset", (C.ASSETS / "survey_stage1.csv").exists(), "python3 _scripts/gen_assets.py", "warn")
    add("ANTHROPIC_API_KEY", bool(os.environ.get("ANTHROPIC_API_KEY")), "unset → clipboard fallback", "info")
    rc = Path.home() / (".zshrc" if "zsh" in os.environ.get("SHELL", "zsh") else ".bashrc")
    add("shell alias `learn`", rc.exists() and "praxis-learn-alias" in rc.read_text(encoding="utf-8", errors="ignore"),
        "learn install-alias", "warn")

    errors = [c for c in checks if c["level"] == "error"]
    warns = [c for c in checks if c["level"] == "warn"]
    lines = [f"{'✅' if c['ok'] else ('❌' if c['level'] == 'error' else '⚠️ ' if c['level'] == 'warn' else 'ℹ️ ')} {c['name']}"
             + (f" — {c['detail']}" if c["detail"] and (not c["ok"] or a.verbose) else "") for c in checks]
    return {"ok": not errors, "checks": checks, "errors": len(errors), "warnings": len(warns), "lines": lines,
            "message": f"doctor: {len(checks)} checks, {len(errors)} error(s), {len(warns)} warning(s)"}


# ==========================================================================
# Launchers & installers
# ==========================================================================


def cmd_game(a) -> dict:
    g = find_godot()
    if not g:
        return {"ok": False, "message": "Godot 4 not found. `brew install --cask godot` or set GODOT_BIN."}
    cmd = [g, "--path", str(C.GAME)]
    if a.editor:
        cmd.insert(1, "-e")
    first_run = not (C.GAME / ".godot").exists()
    import_cmd = [g, "--headless", "--editor", "--quit", "--path", str(C.GAME)]
    if a.dry_run:
        return {"ok": True, "command": cmd, "import_first": first_run,
                "message": "[dry-run] " + (" ".join(import_cmd) + " && " if first_run else "") + " ".join(cmd)}
    if first_run and not a.editor:
        # First launch: let Godot import the project (builds .godot/) before running it.
        try:
            subprocess.run(import_cmd, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            pass
    env = dict(os.environ, PRAXIS_ROOT=str(C.ROOT))
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)
    return {"ok": True, "command": cmd, "message": "🎮 Launching Praxis: The Emergent Grid…"}


def cmd_install_alias(a) -> dict:
    shell = os.environ.get("SHELL", "/bin/zsh")
    rc = Path.home() / (".zshrc" if "zsh" in shell or C.SYSTEM == "Darwin" else ".bashrc")
    line = f"alias learn='python3 \"{C.SCRIPTS / 'learn.py'}\"'  # praxis-learn-alias"
    text = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if "praxis-learn-alias" in text:
        return {"ok": True, "rc": str(rc), "changed": False, "message": f"Alias already in {rc}"}
    if not a.dry_run:
        rc.write_text(text.rstrip("\n") + ("\n" if text else "") + line + "\n", encoding="utf-8")
    return {"ok": True, "rc": str(rc), "changed": not a.dry_run, "line": line,
            "message": f"{'[dry-run] would add' if a.dry_run else 'Added'} to {rc}:\n  {line}\nRun `source {rc}`."}


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.praxis.learn.nightly</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>{python} "{scripts}/make_cards.py" &amp;&amp; {python} "{scripts}/learn.py" sync --headless</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
"""


def cmd_install_scheduler(a) -> dict:
    py = C.python_exe()
    log = C.SCRIPTS / "scheduler" / "nightly.log"
    if C.SYSTEM == "Darwin" or a.platform == "macos":
        plist = PLIST.format(python=py, scripts=C.SCRIPTS, log=log)
        dest = Path.home() / "Library/LaunchAgents/com.praxis.learn.nightly.plist"
        if a.dry_run:
            return {"ok": True, "dest": str(dest), "plist": plist, "message": f"[dry-run] would write {dest} and launchctl load it"}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(plist, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(dest)], capture_output=True)
        r = subprocess.run(["launchctl", "load", str(dest)], capture_output=True, text=True)
        return {"ok": r.returncode == 0, "dest": str(dest), "message": f"Nightly sync scheduled at 02:30 via launchd ({dest})."
                + ("" if r.returncode == 0 else f" launchctl: {r.stderr.strip()}")}
    line = f'30 2 * * * {py} "{C.SCRIPTS}/make_cards.py" && {py} "{C.SCRIPTS}/learn.py" sync --headless >> "{log}" 2>&1 # praxis-nightly'
    if C.SYSTEM == "Windows":
        cmd = f'schtasks /Create /SC DAILY /ST 02:30 /TN PraxisNightly /TR "{py} \\"{C.SCRIPTS}\\learn.py\\" sync --headless"'
        return {"ok": True, "command": cmd, "message": f"Run in PowerShell:\n  {cmd}"}
    if a.dry_run or not shutil.which("crontab"):
        return {"ok": True, "cron": line, "message": f"{'[dry-run] ' if a.dry_run else 'crontab not found; add manually: '}{line}"}
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    if "praxis-nightly" in cur:
        return {"ok": True, "message": "Cron entry already installed."}
    subprocess.run(["crontab", "-"], input=cur.rstrip("\n") + "\n" + line + "\n", text=True)
    return {"ok": True, "cron": line, "message": "Nightly sync added to crontab (02:30)."}


# ==========================================================================
# CLI
# ==========================================================================


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")
    common.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="change nothing")
    common.add_argument("--headless", action="store_true", default=argparse.SUPPRESS, help="never open apps")

    ap = argparse.ArgumentParser(prog="learn", description="Praxis learning OS", parents=[common],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    def sp(name: str, fn, help_: str):
        p = sub.add_parser(name, parents=[common], help=help_)
        p.set_defaults(fn=fn)
        return p

    p = sp("start", cmd_start, "start a deep-work session")
    p.add_argument("track", nargs="?")
    p.add_argument("--file", help="vault-relative file to open")
    p = sp("stop", cmd_stop, "stop the session and log it")
    p.add_argument("--minutes", type=float, help="override elapsed minutes")
    sp("status", cmd_status, "show state")
    p = sp("q", cmd_q, "add an unanswered question")
    p.add_argument("question")
    p = sp("person", cmd_person, 'log "Name: detail"')
    p.add_argument("entry")
    p = sp("highlight", cmd_highlight, "add a >> highlight + flashcard")
    p.add_argument("text")
    p.add_argument("--file")
    p = sp("card", cmd_card, 'add "front :: back" flashcard')
    p.add_argument("card")
    p.add_argument("--file")
    p = sp("pages", cmd_pages, "log pages read today")
    p.add_argument("pages", type=int)
    p = sp("focus", cmd_focus, "set current reading/course/essay/project")
    p.add_argument("key")
    p.add_argument("value")
    p = sp("benchmark", cmd_benchmark, "check off a benchmark id")
    p.add_argument("id")
    p.add_argument("--undo", action="store_true")
    p = sp("run-drone", cmd_run_drone, "run a drone script")
    p.add_argument("script")
    p.add_argument("challenge")
    p.add_argument("--no-commit", action="store_true")
    p = sp("world", cmd_world, "preview a challenge world (JSON)")
    p.add_argument("challenge")
    p = sp("resume", cmd_resume, "rebuild résumé + portfolio (and PDF)")
    p.add_argument("--open", action="store_true")
    p.add_argument("--no-pdf", action="store_true")
    p = sp("critique", cmd_critique, "harsh AI essay critique")
    p.add_argument("essay")
    p.add_argument("--clipboard", action="store_true", help="force clipboard mode")
    p = sp("quiz", cmd_quiz, "flashcard quiz")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--answer", help="card id being answered")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--correct", action="store_true", dest="correct", default=False)
    g.add_argument("--wrong", action="store_false", dest="correct")
    p.add_argument("--ai", action="store_true", help="5-question oral quiz on current reading via AI")
    p.add_argument("--file")
    p = sp("publish", cmd_publish, "publish an essay to the portfolio")
    p.add_argument("essay")
    p.add_argument("--undo", action="store_true")
    p = sp("project", cmd_project, "create a project + git repo")
    p.add_argument("name")
    p.add_argument("--summary", default="")
    p = sp("init-curriculum", cmd_init_curriculum, "switch curriculum cartridge")
    p.add_argument("template", nargs="?")
    p.add_argument("--list", action="store_true")
    p.add_argument("--generate", metavar="GOAL", help="generate a new cartridge for GOAL with AI")
    p = sp("export-public", cmd_export_public, "build the public engine export")
    p.add_argument("--out")
    p.add_argument("--force", action="store_true", help="overwrite a non-empty target")
    p = sp("sync", cmd_sync, "cards + portfolio + git")
    p.add_argument("--push", action="store_true")
    p.add_argument("--public", action="store_true", help="also export & commit the public repo")
    p.add_argument("--out")
    p = sp("doctor", cmd_doctor, "verify installation")
    p.add_argument("--verbose", "-v", action="store_true")
    sp("cards", lambda a: make_cards.run(a.dry_run), "regenerate flashcards")
    p = sp("game", cmd_game, "launch the Godot game")
    p.add_argument("--editor", action="store_true", help="open in the Godot editor")
    sp("install-alias", cmd_install_alias, "add `learn` alias to your shell rc")
    p = sp("install-scheduler", cmd_install_scheduler, "schedule nightly sync")
    p.add_argument("--platform", choices=["auto", "macos", "linux"], default="auto")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    for flag in ("json", "dry_run", "headless"):
        if not hasattr(a, flag):
            setattr(a, flag, False)
    if a.headless:
        os.environ["PRAXIS_NO_OPEN"] = "1"
    if not getattr(a, "fn", None):
        a.track, a.file, a.fn = None, None, cmd_start
    try:
        res = a.fn(a)
    except C.PraxisError as e:
        res = {"ok": False, "error": str(e), "message": f"Error: {e}"}
    except KeyboardInterrupt:
        return 130
    C.emit(res, a.json)
    return 0 if res.get("ok", res.get("success", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
