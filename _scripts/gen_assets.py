#!/usr/bin/env python3
"""Generate the sample datasets used by the drone challenges (deterministic).

Creates ``_assets/survey_stage1.csv``: a synthetic social-media & wellbeing
survey with ~8% missing values. Safe to re-run; use --force to overwrite.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SURVEY = C.ASSETS / "survey_stage1.csv"


def make_survey(path: Path = SURVEY, n: int = 400, seed: int = 1973) -> Path:
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        group = "treatment" if rng.random() < 0.5 else "control"
        age = rng.randint(18, 70)
        hours = max(0.0, rng.gauss(3.2 if group == "treatment" else 2.4, 1.1))
        sleep = max(3.5, min(10.0, rng.gauss(7.1 - 0.15 * hours, 0.9)))
        wellbeing = 62 - 2.1 * hours + 1.4 * (sleep - 7) + 0.05 * (age - 40) + rng.gauss(0, 8)
        wellbeing = max(0.0, min(100.0, wellbeing))
        row = {
            "respondent_id": f"R{i:04d}",
            "age": age,
            "group": group,
            "hours_social_media": round(hours, 2),
            "sleep_hours": round(sleep, 2),
            "wellbeing_score": round(wellbeing, 1),
        }
        r = rng.random()
        if r < 0.04:
            row["wellbeing_score"] = ""  # missing
        elif r < 0.06:
            row["wellbeing_score"] = "NA"  # corrupted
        elif r < 0.08:
            row["hours_social_media"] = ""
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


def restore_starters() -> list[str]:
    """Copy any missing starter drone scripts into code/drones/ (never overwrites)."""
    import shutil

    src = C.SCRIPTS / "starters" / "drones"
    out = []
    if src.is_dir():
        C.DRONES.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.iterdir()):
            dest = C.DRONES / f.name
            if f.is_file() and not dest.exists():
                shutil.copy2(f, dest)
                out.append(C.rel(dest))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    created = []
    if a.force or not SURVEY.exists():
        make_survey()
        created.append(C.rel(SURVEY))
    created += restore_starters()
    C.emit({"ok": True, "created": created, "message": f"Assets ready ({len(created)} generated)."}, a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
