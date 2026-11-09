# Praxis — Setup Notes

Praxis is a local-first learning OS: an Obsidian vault + a Python CLI (`learn`) + a Godot 4 game
(*Praxis: The Emergent Grid*). The CLI and the game read and write the same files —
`_scripts/state.json` and the Markdown notes — so you can use either, or both.


## 1. Install (macOS)

```bash
brew install python git typst            # typst = résumé PDF (optional)
brew install --cask obsidian godot        # Godot 4.3+
git clone https://github.com/johncaden124/praxis-vault.git ~/Learning   # or your own copy
cd ~/Learning
pip3 install -r _scripts/requirements.txt  # use a venv if pip refuses (PEP 668)
python3 _scripts/gen_assets.py            # sample survey dataset + starter drone scripts
python3 _scripts/learn.py install-alias   # adds `alias learn=…` to ~/.zshrc
source ~/.zshrc
learn doctor                              # everything should be ✅ (warnings are optional tools)
```

If you install Python packages in a virtualenv, set `"python_bin": "/path/to/venv/bin/python3"` in
`_scripts/config.json` so the game uses the same interpreter.

## 2. Obsidian

1. Open `~/Learning` as a vault (name it **Learning** — or change `obsidian_vault_name` in `_scripts/config.json`).
2. Settings → Community plugins → turn on, then install & enable:
   **Dataview** (enable *JavaScript queries*), **Templater**, **QuickAdd**, **Spaced Repetition**, **Periodic Notes**, **Homepage**.
   Their settings are already in `.obsidian/plugins/*/data.json`.
3. The dashboard (`00 Dashboard.md`) opens on startup.

| Hotkey | Action |
|---|---|
| Cmd+Shift+T | Open today's note (`02 Today/YYYY-MM-DD.md`) |
| Cmd+Shift+Q | QuickAdd question → `05 Questions.md` |
| Cmd+Shift+P | QuickAdd person detail → `06 People.md` Inbox (filed by `learn sync`) |
| Cmd+Shift+C | QuickAdd flashcard `>> front :: back` into the active note |
| Cmd+Shift+D | Open `00 Dashboard.md` |

## 3. Daily use (terminal)

```bash
learn                      # start the block scheduled for now (schedule.yaml)
learn stop                 # log hours → today's note, +XP, +Cognitive Bandwidth
learn highlight "…"        # >> highlight into current reading + flashcard (+10 bandwidth)
learn card "front :: back"
learn q "question the author didn't answer"
learn person "Sam: just started a PhD in sociology"
learn pages 30
learn quiz                 # 5 flashcards; correct answers recharge bandwidth
learn benchmark s1_stats   # check off a benchmark / gather item → unlocks tech, rebuilds résumé
learn project "weak-ties"  # 07 Projects note + real git repo in code/weak-ties/
learn critique "Essay 01"  # harsh AI critique (or clipboard prompt)
learn publish "Essay 01"   # shows on the portfolio
learn resume --open        # rebuild résumé/portfolio (+PDF) and open it
learn status               # summary;  every command takes --json --dry-run --headless
```

## 4. The game

```bash
learn game          # first launch imports the project, then runs it
learn game --editor # open in the Godot editor
```

Or open `~/Learning/game/project.godot` in Godot and press F5.
Rooms (Alt+1…5): **Automation Grid & IDE**, **Study Sanctum**, **Tech Tree**, **Social Radar**, **Character Sheet**.

The loop: drone steps cost Cognitive Bandwidth → recharge it with a real study session or the flashcard
reactor → passing drone challenges commits your code and checks benchmarks → the Tech Tree unlocks
bigger grids, cheaper steps and sensors → your résumé rebuilds itself.

Drone scripts live in `code/drones/` (edit in the game or VS Code). Test one from the terminal:
`learn run-drone c1_loops.py c1_loops`.

## 5. Nightly automation

```bash
learn install-scheduler     # launchd job at 02:30: make_cards + learn sync
```
Remove with `launchctl unload ~/Library/LaunchAgents/com.praxis.learn.nightly.plist`.

## 6. Dual-repo setup

| Repo | Contains | How it's updated |
|---|---|---|
| **private** `praxis-vault` | the whole vault: daily notes, reviews, people, drafts | `learn sync --push` (nightly job commits; add `--push` to push) |
| **public** `praxis-engine` | engine + game + starter cartridges + your compiled portfolio, no private notes | `learn export-public` then commit/push that folder, or `learn sync --public --push` |

```bash
# once
cd ~/Learning && git remote add origin git@github.com:YOU/praxis-vault.git
git clone git@github.com:YOU/praxis-engine.git ~/Learning_Public_Export
# any time
learn export-public && cd ~/Learning_Public_Export && git add -A && git commit -m "Update" && git push
```

The exporter strips `02 Today/`, `09 Reviews/`, reading notes & cards, unpublished drafts, real
`06 People.md` (replaced by a dummy), your drone solutions and anything inside
``, resets `01 Plan/` and `state.json` to Level 1, and
**blocks the export** if a name from `06 People.md` or an API key shows up anywhere. If a flagged name
is intentional (e.g. a public co-author), add it to `export_allow_names` in `_scripts/config.json`.

Project repos you create with `learn project` are their own git repos (`code/<name>/`) and are
ignored by the vault repo — push each to its own GitHub repo and put the URL in the project note's
`github:` field so it appears on your portfolio.

## 7. Publishing the lead magnet

1. Set `profile` and `praxis_engine_url` in `_scripts/config.json`.
2. `learn export-public` → push `~/Learning_Public_Export` to `praxis-engine`.
3. Turn on **GitHub Pages** for `praxis-engine` (Settings → Pages → branch `main`, folder `/`), and link
   `https://YOU.github.io/praxis-engine/10%20Portfolio/` from your website — or copy `10 Portfolio/` into
   your site. The page ends with the "Try the engine: download Praxis OS" card linking back to the repo.

## 8. Swapping curricula

```bash
learn init-curriculum --list
learn init-curriculum fullstack_ai_engineer    # current plan is backed up to _curriculums/_backup_*/
learn init-curriculum my_plan --generate "Become a marine biologist in 3 years"
```
A cartridge is four files: `Learning Path.md`, `benchmarks.md`, `Gather List.md`,
`curriculum_manifest.yaml`. `learn doctor` validates that every id the manifest references exists.

## 9. Troubleshooting

- `learn doctor -v` shows every check.
- Game says it can't run Python: set `python_bin` in `_scripts/config.json`.
- Godot can't find the vault (exported build): set `PRAXIS_ROOT=~/Learning`.
- Tests: `python3 -m pytest _scripts/tests -q`.
