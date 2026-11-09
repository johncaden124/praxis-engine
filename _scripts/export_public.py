#!/usr/bin/env python3
"""Export a sanitized, shareable copy of the Praxis engine (+ your portfolio).

    python3 export_public.py [--out DIR] [--json] [--dry-run] [--force]

The output is what goes into the public `praxis-engine` repository / website
download. It contains the engine and your *public* work, never private notes:

INCLUDED   game/, _scripts/ (fresh state, placeholder profile), _templates/,
           .obsidian/ config, _curriculums/ starter packs, starter drone
           scripts, public project repos (07 Projects with public: true,
           without their .git), essays with `status: published`, and the
           compiled 10 Portfolio/.
EXCLUDED   02 Today/ daily logs, 09 Reviews/, unpublished drafts, reading
           notes & cards, 05 Questions, real 06 People.md (replaced with a
           2-line dummy), your drone solutions, cartridge backups, logs,
           and any block wrapped in <!-- private:start --> … <!-- private:end -->.

01 Plan/ is reset to the default cartridge and state.json to a fresh Level 1,
so anyone who downloads it starts at the beginning. A leak scan runs last and
fails the export if anything private slipped through.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MARKER = ".praxis-export"
DEFAULT_CARTRIDGE = "computational_social_science"
PRIVATE_BLOCK = re.compile(r"<!-- private:start -->.*?<!-- private:end -->\n?", re.S)
SKIP_NAMES = {"__pycache__", ".DS_Store", ".godot", ".pytest_cache", "workspace.json", "workspace-mobile.json",
              "nightly.log", ".last_prompt.md", ".git"}
TEXT_EXT = {".md", ".py", ".gd", ".tscn", ".godot", ".json", ".yaml", ".yml", ".txt", ".html", ".cfg", ".csv", ".toml", ".gitignore"}

DUMMY_PEOPLE = """---
tags: [people, private]
---

# People

Private CRM and interaction log — this file is never exported from your own vault.
Add with `learn person "Name: detail"`, the in-game Social Radar, or Cmd+Shift+P.

## Inbox

## Example Mentor
- 2026-01-01 — Example entry: recommended reading Granovetter before Christakis.
"""

QUESTIONS = """---
tags: [questions]
---

# Questions the Author Didn't Answer

Add with `learn q "<question>"`, the in-game Quick Capture bar, or Cmd+Shift+Q.

"""

PUBLIC_GITIGNORE = """# Praxis — public engine
__pycache__/
*.pyc
.DS_Store
game/.godot/
game/*.translation
.obsidian/workspace*.json
_scripts/scheduler/*.log
_scripts/prompts/.last_prompt.md
_curriculums/_backup_*/
"""

MIT = """MIT License

Copyright (c) 2026 Praxis contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def readme(engine_url: str, cartridges: list[str]) -> str:
    clone = engine_url.rstrip("/") + ".git" if engine_url else "<this repo>"
    packs = "\n".join(f"| `{c}` | `learn init-curriculum {c}` |" for c in cartridges)
    return f"""# Praxis: The Diegetic Learning OS & Automation Game

> Program a research drone in **real Python**. Recharge it by **actually studying**. Watch your **résumé rebuild itself**.

Praxis is a local-first learning operating system for self-directed learners. It pairs a plain-text
[Obsidian](https://obsidian.md) vault with a Godot 4 automation game — *Praxis: The Emergent Grid* — in which
nothing stays in the game: every action reads and writes real Markdown, JSON and git repositories on your disk.

```
            ┌───────────────────────────── ~/Learning ─────────────────────────────┐
            │                                                                       │
 terminal ──┤  learn start / stop / q / person / highlight / benchmark / quiz …     │
            │        │                                                              │
            │        ▼                                                              │
            │  _scripts/learn.py ──► _scripts/state.json ◄── game/ (Godot 4)        │
            │        │   ▲                 ▲  OS.execute(learn.py --json)           │
            │        │   └── drone_runner.py ◄── code/drones/*.py (your Python)     │
            │        ▼                                                              │
            │  01 Plan/  benchmarks.md · Gather List.md · curriculum_manifest.yaml  │
            │  02 Today/ 03 Reading/ 04 Writing/ 06 People.md 08 Cards/ …           │
            │        │                                                              │
            │        ▼                                                              │
            │  10 Portfolio/ resume.json · index.html · resume.pdf  ──► your website │
            └───────────────────────────────────────────────────────────────────────┘
```

## The loop

| You do this in real life… | …and the game reacts |
|---|---|
| Write Python for your drone (in-game IDE or VS Code) | It runs against real datasets, animates on the grid, and passing code is **git-committed** |
| Run a deep-work timer (`learn start` → `learn stop`) | Hours land in today's note; the drone gets **Cognitive Bandwidth** (energy) and you get XP |
| Capture `>>` highlights from your reading | They become spaced-repetition **flashcards**; the in-game quiz recharges bandwidth |
| Check off a curriculum benchmark | The **Tech Tree** unlocks bigger grids, cheaper steps, new sensors — and your résumé recompiles |
| Log a conversation in `06 People.md` | The **Social Topology Radar** lights the person up; dormant ties pulse red after 30 days |
| Publish an essay | It appears on your portfolio site |

## Quick start (macOS)

```bash
brew install python git
brew install --cask godot obsidian       # Godot 4.3+
brew install typst                       # optional: résumé PDF

git clone {clone} ~/Learning
cd ~/Learning
pip3 install -r _scripts/requirements.txt
python3 _scripts/gen_assets.py
python3 _scripts/learn.py install-alias  # adds `learn` to ~/.zshrc
source ~/.zshrc

learn doctor          # verify everything
learn                 # start today's scheduled study block
learn game            # launch Praxis: The Emergent Grid
```

Linux works the same (`xdg-open`, `cron`); Windows works with the `python` launcher and PowerShell.
Open `~/Learning` as an Obsidian vault and install the community plugins listed in `SETUP_NOTES.md`.

## Bring your own curriculum

The engine is curriculum-agnostic. Everything the game shows — tracks, stages, benchmarks, tech-tree
rewards — comes from four files in `01 Plan/`:

| File | Purpose |
|---|---|
| `Learning Path.md` | Human-readable plan |
| `benchmarks.md` | `- [ ] (`id`) …` checkboxes the engine checks off |
| `Gather List.md` | Books, courses, tools — also checkboxes with ids |
| `curriculum_manifest.yaml` | Tracks, stages, credentials, skills, tech tree, challenges |

Starter cartridges:

| Cartridge | Install |
|---|---|
{packs}

Or generate one for any goal: `learn init-curriculum my_plan --generate "Become a marine biologist"`
(uses `ANTHROPIC_API_KEY` if set; otherwise copies the prompt to your clipboard).

## Drone challenges

| # | Challenge | Concept |
|---|---|---|
| 1 | Survey Sweep | loops, sequencing |
| 2 | CSV & Descriptive Stats | pandas, cleaning, Welch t-test, plotting |
| 3 | Weak Ties | BFS, betweenness centrality (Granovetter) |
| 4 | Yield Regression | gradient descent in NumPy |
| 5 | Schelling Segregation | agent-based modelling, emergence |

```python
from station_api import move, scan, harvest_data, clean_outlier, run_abm_step, plot_csv, submit_result
```

## Privacy by design: two repos

Your full vault (daily notes, reviews, people, drafts) lives in a **private** repo. `learn export-public`
produces this sanitized engine + portfolio for a **public** repo: personal notes are stripped, the
curriculum and game state are reset to Level 1, and a leak scan blocks the export if anything private slips through.

## License

MIT — see `LICENSE`.
"""


# --------------------------------------------------------------------------


def _ignore(dirpath: str, names: list[str]) -> set[str]:
    out = {n for n in names if n in SKIP_NAMES or n.endswith(".pyc")}
    if Path(dirpath).name == "_curriculums":
        out |= {n for n in names if n.startswith("_backup_")}
    return out


def _copytree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)


def _strip_private_blocks(root: Path) -> int:
    n = 0
    for p in root.rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        new = PRIVATE_BLOCK.sub("", t)
        if new != t:
            p.write_text(new, encoding="utf-8")
            n += 1
    return n


def fresh_state(cart_manifest: dict) -> dict:
    s = copy.deepcopy(C.DEFAULT_STATE)
    s["curriculum_name"] = cart_manifest.get("name", "Untitled Curriculum")
    s["current_focus"] = {"reading": "03 Reading/How to Read a Book.md", "course": "CS50x",
                          "essay": "04 Writing/Essay 01.md", "project": None}
    base = [t["id"] for t in cart_manifest.get("tech_tree") or [] if not t.get("unlocked_by")]
    s["unlocked_tech"] = base or ["drone_move_basic", "grid_3x3"]
    s["people_nodes"] = [{"name": "Example Mentor", "last_contact": "2026-01-01", "days_since": 0,
                          "notes_count": 1, "status": "active"}]
    return s


def public_config() -> dict:
    cfg = C.config()
    return {
        "profile": {"name": "Your Name", "label": "What you are learning", "email": "", "website": "",
                    "github": "", "location": "",
                    "summary": "Self-directed learner. This résumé is generated automatically by Praxis."},
        "praxis_engine_url": cfg.get("praxis_engine_url", ""),
        "obsidian_vault_name": "Learning",
        "model": cfg.get("model", "claude-opus-5-5"),
        "godot_bin": "",
        "public_export_dir": "~/Learning_Public_Export",
    }


def private_names() -> list[str]:
    if not C.PEOPLE.exists():
        return []
    allow = set(C.config().get("export_allow_names", [])) | {"Example Mentor", "Inbox"}
    return [m.group(1).strip() for m in re.finditer(r"^## (.+)$", C.PEOPLE.read_text(encoding="utf-8"), re.M)
            if m.group(1).strip() not in allow and len(m.group(1).strip()) >= 3]


def leak_scan(out: Path) -> list[str]:
    problems = []
    for d in ("02 Today", "09 Reviews", "08 Cards"):
        extra = [p for p in (out / d).rglob("*") if p.is_file() and p.name != ".gitkeep"] if (out / d).exists() else []
        problems += [f"private file exported: {p.relative_to(out)}" for p in extra]
    people = out / "06 People.md"
    if people.exists() and people.read_text(encoding="utf-8") != DUMMY_PEOPLE:
        problems.append("06 People.md is not the dummy")
    for p in (out / "04 Writing").glob("*.md") if (out / "04 Writing").exists() else []:
        fm, _ = C.read_frontmatter(p)
        if str(fm.get("status", "")).lower() != "published" and p.name != "Essay 01.md":
            problems.append(f"unpublished draft exported: {p.relative_to(out)}")
    names = private_names()
    key_re = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}|sk-[A-Za-z0-9]{32,}")
    name_res = [(n, re.compile(rf"\b{re.escape(n)}\b")) for n in names]
    for p in out.rglob("*"):
        if not p.is_file() or ".git" in p.parts or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if key_re.search(t):
            problems.append(f"possible API key in {p.relative_to(out)}")
        is_template = p.relative_to(out).parts[0] in ("_templates", "_curriculums", "_scripts")
        if (p.suffix == ".md" and not is_template and p.name != "06 People.md"
                and "private" in str((C.read_frontmatter(p)[0] or {}).get("tags", ""))):
            problems.append(f"file tagged private exported: {p.relative_to(out)}")
        for n, rx in name_res:
            if rx.search(t):
                problems.append(f"name from 06 People.md ('{n}') found in {p.relative_to(out)} "
                                f"(add to config.json export_allow_names if this is intentional)")
    return problems


def _check_target(out: Path, force: bool) -> None:
    root = C.ROOT.resolve()
    o = out.resolve()
    if o == root or root in o.parents or o in root.parents:
        raise C.PraxisError(f"Refusing to export into/around the vault itself: {o}")
    if not o.exists() or force or (o / MARKER).exists():
        return
    leftovers = [p.name for p in o.iterdir() if p.name != ".git" and not p.name.upper().startswith(("README", "LICENSE"))]
    if leftovers:
        raise C.PraxisError(f"{o} is not empty and is not a previous Praxis export ({leftovers[:5]}). Use --force to overwrite.")


def run(out: Path | None = None, dry_run: bool = False, force: bool = False) -> dict:
    out = (out or Path(os.path.expanduser(C.config().get("public_export_dir", "~/Learning_Public_Export")))).expanduser()
    _check_target(out, force)
    cart = C.CURRICULUMS / DEFAULT_CARTRIDGE
    if not cart.is_dir():
        raise C.PraxisError(f"Default cartridge missing: {C.rel(cart)}")
    published = []
    for p in sorted(C.WRITING.glob("*.md")) if C.WRITING.exists() else []:
        fm, _ = C.read_frontmatter(p)
        if str(fm.get("status", "")).lower() == "published":
            published.append(p)
    public_projects = []
    for p in sorted(C.PROJECTS.glob("*.md")) if C.PROJECTS.exists() else []:
        fm, _ = C.read_frontmatter(p)
        if fm.get("public") is True or str(fm.get("public")).lower() == "true":
            public_projects.append((p, str(fm.get("repo") or "")))
    plan = {"out": str(out), "published_essays": [C.rel(p) for p in published],
            "public_projects": [C.rel(p) for p, _ in public_projects]}
    if dry_run:
        return {"ok": True, "dry_run": True, **plan,
                "message": f"[dry-run] would export to {out}: {len(published)} essay(s), {len(public_projects)} project(s)"}

    # 1. clean target (keep .git)
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()

    # 2. engine
    for d in ("game", "_scripts", "_templates", ".obsidian", "_curriculums"):
        _copytree(C.ROOT / d, out / d)
    (out / "_scripts" / "state.json").unlink(missing_ok=True)
    for f in ("config.json",):
        (out / "_scripts" / f).unlink(missing_ok=True)
    (out / "_scripts" / "config.json").write_text(json.dumps(public_config(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 3. cartridge reset
    (out / "01 Plan").mkdir(exist_ok=True)
    for f in ("Learning Path.md", "Gather List.md", "benchmarks.md", "curriculum_manifest.yaml"):
        shutil.copy2(cart / f, out / "01 Plan" / f)
    cart_manifest = C.load_yaml(cart / "curriculum_manifest.yaml") or {}
    state = fresh_state(cart_manifest)
    (out / "_scripts" / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "01 Plan" / "state.md").write_text(
        "---\nstage: 1\nstage_name: Foundations\nxp: 0\nstreak_days: 0\n---\n\n# Current State\n\n"
        "Mirrors `_scripts/state.json`; rewritten by `learn` after every change.\n", encoding="utf-8")

    # 4. vault notes: templates / dummies only
    for d in ("02 Today", "08 Cards", "09 Reviews", "_assets", "07 Projects", "03 Reading", "04 Writing", "code/drones"):
        (out / d).mkdir(parents=True, exist_ok=True)
    for d in ("02 Today", "08 Cards", "09 Reviews", "_assets"):
        (out / d / ".gitkeep").write_text("", encoding="utf-8")
    starters = C.SCRIPTS / "starters"
    shutil.copy2(starters / "How to Read a Book.md", out / "03 Reading" / "How to Read a Book.md")
    shutil.copy2(starters / "Essay 01.md", out / "04 Writing" / "Essay 01.md")
    _copytree(starters / "drones", out / "code" / "drones")
    for p in published:
        shutil.copy2(p, out / "04 Writing" / p.name)
    (out / "06 People.md").write_text(DUMMY_PEOPLE, encoding="utf-8")
    (out / "05 Questions.md").write_text(QUESTIONS, encoding="utf-8")
    shutil.copy2(C.ROOT / "00 Dashboard.md", out / "00 Dashboard.md")
    if (C.ROOT / "SETUP_NOTES.md").exists():
        shutil.copy2(C.ROOT / "SETUP_NOTES.md", out / "SETUP_NOTES.md")
    survey = C.ASSETS / "survey_stage1.csv"
    if survey.exists():
        shutil.copy2(survey, out / "_assets" / survey.name)

    # 5. public projects (notes + code without .git)
    exported_projects = []
    for note, repo in public_projects:
        shutil.copy2(note, out / "07 Projects" / note.name)
        src = C.ROOT / repo if repo else None
        if src and src.is_dir() and src.resolve() != C.DRONES.resolve():
            _copytree(src, out / repo)
        exported_projects.append(note.stem)

    # 6. portfolio (compiled)
    (out / "10 Portfolio").mkdir(exist_ok=True)
    for f in ("build_resume.py", "index.html", "resume.json", "resume.pdf"):
        if (C.PORTFOLIO / f).exists():
            shutil.copy2(C.PORTFOLIO / f, out / "10 Portfolio" / f)
    _copytree(C.PORTFOLIO / "essays", out / "10 Portfolio" / "essays")

    # 7. docs
    stripped = _strip_private_blocks(out)
    cartridges = sorted(p.name for p in (out / "_curriculums").iterdir() if p.is_dir() and not p.name.startswith("_"))
    (out / "README.md").write_text(readme(C.config().get("praxis_engine_url", ""), cartridges), encoding="utf-8")
    (out / "LICENSE").write_text(MIT, encoding="utf-8")
    (out / ".gitignore").write_text(PUBLIC_GITIGNORE, encoding="utf-8")
    (out / MARKER).write_text("This folder is generated by `learn export-public`. Do not edit by hand.\n", encoding="utf-8")

    problems = leak_scan(out)
    files = sum(1 for p in out.rglob("*") if p.is_file() and ".git" not in p.parts)
    return {"ok": not problems, **plan, "files": files, "public_projects_exported": exported_projects,
            "private_blocks_stripped": stripped, "leaks": problems,
            "message": (f"Public engine exported to {out} ({files} files)." if not problems else
                        f"EXPORT BLOCKED — {len(problems)} possible leak(s):\n  " + "\n  ".join(problems))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = run(Path(a.out) if a.out else None, a.dry_run, a.force)
    except C.PraxisError as e:
        res = {"ok": False, "error": str(e), "message": f"Error: {e}"}
    C.emit(res, a.json)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
