# Praxis: The Diegetic Learning OS & Automation Game

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

git clone https://github.com/johncaden124/praxis-engine.git ~/Learning
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
| `blank_custom_template` | `learn init-curriculum blank_custom_template` |
| `computational_social_science` | `learn init-curriculum computational_social_science` |
| `fullstack_ai_engineer` | `learn init-curriculum fullstack_ai_engineer` |

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
