#!/usr/bin/env python3
"""Extract `>>` highlights from 03 Reading/ into flashcards in 08 Cards/.

Card format is compatible with the Obsidian Spaced Repetition plugin:

    #flashcard
    Front text::Back text
    <!--SR:!2026-11-12,3,250-->      (added after a review)

A highlight written as `>> front :: back` becomes that exact card. A plain
highlight `>> some sentence` becomes a recall card whose front is a prompt
built from the note title and the first words of the sentence.

The script is idempotent: existing cards (and their review history) are never
rewritten, only new ones are appended.

Usage: python3 make_cards.py [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

HL_RE = re.compile(r"^\s*>>\s?(?P<body>.+?)\s*$")
CARD_RE = re.compile(r"^(?P<front>[^#<>\n].*?)::(?P<back>.+?)\s*$")
SR_RE = re.compile(r"<!--SR:!(?P<due>\d{4}-\d{2}-\d{2}),(?P<interval>\d+),(?P<ease>\d+)-->")


def card_id(front: str) -> str:
    return hashlib.sha1(front.strip().lower().encode("utf-8")).hexdigest()[:10]


def highlight_to_card(title: str, body: str) -> tuple[str, str]:
    if "::" in body:
        front, back = body.split("::", 1)
        return front.strip(), back.strip()
    words = body.split()
    lead = " ".join(words[:6])
    front = f"[{title}] Complete the idea: \"{lead}…\""
    return front, body.strip()


def extract_highlights(note: Path) -> list[tuple[str, str]]:
    fm, body = C.read_frontmatter(note)
    title = str(fm.get("title") or note.stem)
    cards = []
    in_code = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HL_RE.match(line)
        if m and m.group("body").strip():
            cards.append(highlight_to_card(title, m.group("body")))
    return cards


def cards_file_for(note: Path) -> Path:
    return C.CARDS / f"{note.stem}.md"


def existing_fronts(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = CARD_RE.match(line)
        if m:
            out.add(card_id(m.group("front")))
    return out


def run(dry_run: bool = False) -> dict:
    created: list[dict] = []
    if not C.READING.exists():
        return {"ok": True, "created": [], "cards_due": 0, "message": "No 03 Reading/ folder."}
    for note in sorted(C.READING.glob("*.md")):
        hl = extract_highlights(note)
        if not hl:
            continue
        target = cards_file_for(note)
        have = existing_fronts(target)
        new = [(f, b) for f, b in hl if card_id(f) not in have]
        # dedupe within the same note
        seen: set[str] = set()
        new = [(f, b) for f, b in new if not (card_id(f) in seen or seen.add(card_id(f)))]
        if not new:
            continue
        if target.exists():
            text = target.read_text(encoding="utf-8").rstrip("\n") + "\n"
        else:
            text = (
                f"---\ntype: cards\nsource: \"[[{note.stem}]]\"\ntags: [cards]\n---\n\n"
                f"# Cards — {note.stem}\n\n#flashcard\n\n"
            )
        for f, b in new:
            text += f"{f}::{b}\n\n"
            created.append({"id": card_id(f), "front": f, "back": b, "file": C.rel(target)})
        if not dry_run:
            C.atomic_write(target, text)
    due = count_due()
    if not dry_run:
        state = C.load_state()
        state["weekly_stats"]["cards_due"] = due
        C.save_state(state)
    return {
        "ok": True,
        "dry_run": dry_run,
        "created": created,
        "cards_due": due,
        "message": f"{len(created)} new card(s); {due} due.",
    }


# --------------------------------------------------------------------------
# Card store used by `learn quiz`
# --------------------------------------------------------------------------


def load_cards() -> list[dict]:
    cards = []
    if not C.CARDS.exists():
        return cards
    for path in sorted(C.CARDS.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("<!--") or line.startswith("---"):
                continue
            m = CARD_RE.match(line)
            if not m:
                continue
            front, back = m.group("front").strip(), m.group("back").strip()
            if not front or front.startswith(("type", "source", "tags", "#")):
                continue
            sr = None
            for j in (i, i + 1):
                if j < len(lines):
                    s = SR_RE.search(lines[j])
                    if s:
                        sr = s
                        break
            due = sr.group("due") if sr else None
            cards.append(
                {
                    "id": card_id(front),
                    "front": front,
                    "back": back,
                    "file": C.rel(path),
                    "due": due,
                    "interval": int(sr.group("interval")) if sr else 0,
                    "ease": int(sr.group("ease")) if sr else 250,
                    "is_due": (due is None) or (due <= C.today_str()),
                }
            )
    return cards


def count_due() -> int:
    return sum(1 for c in load_cards() if c["is_due"])


def review_card(cid: str, correct: bool, dry_run: bool = False) -> dict | None:
    """SM-2-lite scheduling written in the Spaced Repetition plugin's format."""
    for path in sorted(C.CARDS.glob("*.md")) if C.CARDS.exists() else []:
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = CARD_RE.match(line)
            if not m or card_id(m.group("front")) != cid:
                continue
            sr_line = None
            for j in (i, i + 1):
                if j < len(lines) and SR_RE.search(lines[j]):
                    sr_line = j
                    break
            interval, ease = 0, 250
            if sr_line is not None:
                s = SR_RE.search(lines[sr_line])
                interval, ease = int(s.group("interval")), int(s.group("ease"))
            if correct:
                interval = 1 if interval == 0 else max(interval + 1, round(interval * ease / 100))
                ease = min(ease + 10, 350)
            else:
                interval = 1
                ease = max(130, ease - 20)
            due = (C.today() + dt.timedelta(days=interval)).isoformat()
            tag = f"<!--SR:!{due},{interval},{ease}-->"
            if sr_line is None:
                lines.insert(i + 1, tag)
            elif sr_line == i:
                lines[i] = SR_RE.sub(tag, lines[i])
            else:
                lines[sr_line] = SR_RE.sub(tag, lines[sr_line])
            if not dry_run:
                C.atomic_write(path, "\n".join(lines) + "\n")
            return {"id": cid, "due": due, "interval": interval, "ease": ease}
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    C.emit(run(a.dry_run), a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
