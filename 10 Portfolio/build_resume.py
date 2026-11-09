#!/usr/bin/env python3
"""Build the living résumé + portfolio from the vault.

Reads 01 Plan/benchmarks.md, Gather List.md, curriculum_manifest.yaml,
07 Projects/*.md, published 04 Writing/*.md, and _scripts/state.json, then
writes (all inside 10 Portfolio/):

  resume.json     JSON Resume schema (basics, education, certificates, projects, publications, skills)
  index.html      self-contained portfolio + print-ready résumé + "Download Praxis" lead-magnet card
  essays/*.html   published essays
  resume.pdf      if typst / weasyprint / wkhtmltopdf / Chrome / Playwright is available

Usage: python3 build_resume.py [--json] [--no-pdf] [--open]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_scripts"))
import common as C  # noqa: E402

OUT_JSON = C.PORTFOLIO / "resume.json"
OUT_HTML = C.PORTFOLIO / "index.html"
OUT_PDF = C.PORTFOLIO / "resume.pdf"
ESSAY_DIR = C.PORTFOLIO / "essays"

# --------------------------------------------------------------------------
# Data collection
# --------------------------------------------------------------------------


def collect() -> dict:
    state = C.load_state()
    man = C.manifest()
    cfg = C.config()
    profile = {"name": "Your Name", "label": "", "email": "", "website": "", "github": "", "location": "", "summary": ""}
    profile.update(cfg.get("profile") or {})
    items = C.all_checklist_items()
    done = {i["id"] for i in items if i["done"]} | set(state["lifetime_stats"].get("challenges_passed", []))
    by_id = {i["id"]: i for i in items}

    tracks = []
    for t in man.get("tracks") or []:
        ids = t.get("items") or []
        d = sum(1 for i in ids if i in done)
        tracks.append({"label": t["label"], "color": t.get("color", "#39d98a"), "done": d, "total": len(ids),
                       "pct": round(100 * d / len(ids)) if ids else 0,
                       "hours": round(state["lifetime_stats"].get(t.get("hours_key", ""), 0), 1)})

    creds = []
    for cid, meta in (man.get("credentials") or {}).items():
        if cid in done:
            creds.append({"id": cid, "name": meta.get("name", cid), "issuer": meta.get("issuer", ""),
                          "text": by_id.get(cid, {}).get("text", "")})

    benchmarks = [i for i in items if i["file"] == C.BENCHMARKS.name and not i["id"].startswith("cred_")]
    courses = [i for i in items if i["done"] and i["file"] == C.GATHER.name and i["subsection"].lower() == "courses"]
    readings = [i for i in items if i["done"] and i["file"] == C.GATHER.name
                and i["subsection"].lower() in ("books", "philosophy", "free textbooks")]

    skills = [s for s in man.get("skills") or [] if all(r in done for r in s.get("requires") or [])]

    projects = []
    for p in sorted(C.PROJECTS.glob("*.md")) if C.PROJECTS.exists() else []:
        fm, body = C.read_frontmatter(p)
        if fm.get("public") is False or str(fm.get("public")).lower() == "false":
            continue
        plot = str(fm.get("plot") or "")
        projects.append({
            "name": str(fm.get("title") or p.stem), "summary": str(fm.get("summary") or ""),
            "status": str(fm.get("status") or "active"), "github": str(fm.get("github") or ""),
            "repo": str(fm.get("repo") or ""), "skills": list(fm.get("skills") or []),
            "plot": plot, "started": str(fm.get("started") or ""),
        })

    essays = []
    for p in sorted(C.WRITING.glob("*.md")) if C.WRITING.exists() else []:
        fm, body = C.read_frontmatter(p)
        if str(fm.get("status", "")).lower() != "published":
            continue
        clean = body.split("\n## Critique", 1)[0]
        essays.append({"title": str(fm.get("title") or p.stem), "slug": C.slugify(p.stem),
                       "date": str(fm.get("published") or fm.get("due") or ""),
                       "words": len(re.findall(r"\b\w+\b", clean)), "body": clean, "source": p})

    hours = {k[6:]: round(v, 1) for k, v in state["lifetime_stats"].items() if k.startswith("hours_")}
    return {"state": state, "man": man, "cfg": cfg, "profile": profile, "tracks": tracks, "creds": creds,
            "benchmarks": benchmarks, "courses": courses, "readings": readings, "skills": skills,
            "projects": projects, "essays": essays, "hours": hours, "done": done,
            "stage": C.stage_info(state["stage"]), "engine_url": cfg.get("praxis_engine_url", "")}


# --------------------------------------------------------------------------
# JSON Resume
# --------------------------------------------------------------------------


def resume_json(d: dict) -> dict:
    p = d["profile"]
    st = d["state"]
    profiles = []
    if p.get("github"):
        profiles.append({"network": "GitHub", "username": p["github"], "url": f"https://github.com/{p['github']}"})
    return {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "basics": {"name": p["name"], "label": p.get("label", ""), "email": p.get("email", ""),
                   "url": p.get("website", ""), "summary": p.get("summary", ""),
                   "location": {"city": p.get("location", "")}, "profiles": profiles},
        "education": [{
            "institution": "Self-directed curriculum (Praxis Learning OS)",
            "area": st["curriculum_name"],
            "studyType": f"Stage {st['stage']}: {d['stage'].get('name', '')}",
            "score": f"{sum(d['hours'].values()):.0f} logged study hours",
            "courses": [c["text"] for c in d["courses"]],
        }],
        "certificates": [{"name": c["name"], "issuer": c["issuer"]} for c in d["creds"]],
        "projects": [{"name": pr["name"], "description": pr["summary"], "url": pr["github"],
                      "keywords": pr["skills"], "startDate": pr["started"]} for pr in d["projects"]],
        "publications": [{"name": e["title"], "publisher": "Portfolio", "releaseDate": e["date"],
                          "url": f"essays/{e['slug']}.html", "summary": f"{e['words']} words"} for e in d["essays"]],
        "skills": [{"name": s["name"], "level": s.get("level", "")} for s in d["skills"]],
        "meta": {
            "generator": "Praxis build_resume.py",
            "lastModified": C.now().isoformat(),
            "praxis": {"stage": st["stage"], "xp": st["xp"], "streak_days": st["streak_days"],
                       "hours": d["hours"], "benchmarks_completed": sorted(i["id"] for i in d["benchmarks"] if i["done"]),
                       "challenges_passed": st["lifetime_stats"].get("challenges_passed", [])},
        },
    }


# --------------------------------------------------------------------------
# Markdown → HTML (tiny, dependency-free)
# --------------------------------------------------------------------------


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[\[([^\]|]+)\|?([^\]]*)\]\]", lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_html(md: str) -> str:
    out, para, lst = [], [], None

    def flush():
        nonlocal para, lst
        if para:
            out.append("<p>" + md_inline(" ".join(para)) + "</p>")
            para = []
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{md_inline(x)}</li>" for x in lst[1]) + f"</{lst[0]}>")
            lst = None

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{md_inline(m.group(2))}</h{lvl}>")
        elif s.startswith(">"):
            flush()
            out.append(f"<blockquote>{md_inline(s.lstrip('> '))}</blockquote>")
        elif re.match(r"^[-*]\s+", s):
            if para:
                flush()
            if not lst or lst[0] != "ul":
                flush()
                lst = ["ul", []]
            lst[1].append(re.sub(r"^[-*]\s+(\[[ xX]\]\s+)?", "", s))
        elif re.match(r"^\d+\.\s+", s):
            if not lst or lst[0] != "ol":
                flush()
                lst = ["ol", []]
            lst[1].append(re.sub(r"^\d+\.\s+", "", s))
        else:
            if lst:
                flush()
            para.append(s)
    flush()
    return "\n".join(out)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#0b0f14;--panel:#121923;--ink:#e6edf3;--muted:#8b98a7;--line:#223040;--accent:#39d98a;--accent2:#4fc3f7;--warn:#ffb74d;
--serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;--mono:"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f7f8fa;--panel:#fff;--ink:#14202b;--muted:#5b6876;--line:#dde3ea;--accent:#13834f;--accent2:#0b6fa4}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--sans)}
a{color:var(--accent2)}
.wrap{max-width:980px;margin:0 auto;padding:40px 16px 80px}
header.hero{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:24px}
h1{font:600 2.4rem/1.1 var(--serif);margin:0}
.label{color:var(--muted);margin-top:6px}
.links a{margin-right:14px;font-size:.95rem}
.badge{font:600 .8rem var(--mono);color:var(--accent);border:1px solid var(--accent);border-radius:999px;padding:4px 12px;white-space:nowrap}
.summary{font:1.08rem/1.65 var(--serif);max-width:68ch;margin:20px 0 0}
h2{font:600 .85rem var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:44px 0 14px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font:600 1.6rem var(--mono)}.stat span{color:var(--muted);font-size:.85rem}
.bar{margin:10px 0}.bar .top{display:flex;justify-content:space-between;font-size:.92rem}
.bar .track{height:8px;background:var(--line);border-radius:99px;overflow:hidden;margin-top:6px}
.bar .fill{height:100%;border-radius:99px}
.muted{color:var(--muted)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.card h3{margin:0 0 6px;font:600 1.1rem var(--serif)}
.card img{width:100%;border-radius:8px;margin-top:10px;border:1px solid var(--line)}
.tags span{display:inline-block;font:.75rem var(--mono);color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 7px;margin:6px 6px 0 0}
ul.clean{list-style:none;padding:0;margin:0}ul.clean li{padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;justify-content:space-between}
.check{font-family:var(--mono);color:var(--accent)}.todo{font-family:var(--mono);color:var(--muted)}
.heat{display:grid;grid-template-columns:repeat(16,1fr);gap:3px;max-width:520px}
.heat i{aspect-ratio:1;border-radius:3px;background:var(--line);display:block}
.cta{margin-top:56px;border:1px solid var(--accent);border-radius:16px;padding:28px;background:linear-gradient(135deg,rgba(57,217,138,.10),rgba(79,195,247,.08))}
.cta h2{color:var(--accent);margin-top:0}
.cta pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;overflow-x:auto;font:.85rem var(--mono)}
.btn{display:inline-block;background:var(--accent);color:#04120a;font-weight:600;text-decoration:none;border-radius:8px;padding:10px 18px;margin:8px 10px 0 0}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
footer{margin-top:40px;color:var(--muted);font-size:.85rem}
article.essay{max-width:68ch;font:1.1rem/1.75 var(--serif)}article.essay h2,article.essay h3{font-family:var(--serif);text-transform:none;letter-spacing:0;color:var(--ink);font-size:1.3rem}
@media (max-width:640px){header.hero{grid-template-columns:1fr}h1{font-size:2rem}}
@media print{:root{--bg:#fff;--panel:#fff;--ink:#000;--muted:#444;--line:#ccc;--accent:#000;--accent2:#000}
.cta,.heat-wrap,.no-print{display:none!important}.wrap{padding:0}h2{margin-top:22px}.card{break-inside:avoid}body{font-size:11pt}}
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def heatmap(state: dict, weeks: int = 16) -> str:
    log = state.get("daily_log", {})
    t = C.today()
    start = t - dt.timedelta(days=t.weekday() + 7 * (weeks - 1))
    cells = []
    for dow in range(7):
        for w in range(weeks):
            d = start + dt.timedelta(days=7 * w + dow)
            h = float((log.get(d.isoformat()) or {}).get("hours", 0)) if d <= t else 0
            alpha = 0 if h <= 0 else min(1.0, 0.25 + h / 3)
            style = f' style="background:rgba(57,217,138,{alpha:.2f})"' if alpha else ""
            cells.append(f'<i title="{d.isoformat()}: {h:g}h"{style}></i>')
    return f'<div class="heat">{"".join(cells)}</div>'


def render_html(d: dict, rj: dict) -> str:
    p, st = d["profile"], d["state"]
    total_h = sum(d["hours"].values())
    links = []
    if p.get("website"):
        links.append(f'<a href="{esc(p["website"])}">{esc(p["website"]).replace("https://", "")}</a>')
    if p.get("github"):
        links.append(f'<a href="https://github.com/{esc(p["github"])}">github.com/{esc(p["github"])}</a>')
    if p.get("email"):
        links.append(f'<a href="mailto:{esc(p["email"])}">{esc(p["email"])}</a>')
    bars = "".join(
        f'<div class="bar"><div class="top"><span>{esc(t["label"])}</span><span class="muted">{t["done"]}/{t["total"]} · {t["hours"]:g}h</span></div>'
        f'<div class="track"><div class="fill" style="width:{t["pct"]}%;background:{esc(t["color"])}"></div></div></div>'
        for t in d["tracks"])
    creds = "".join(f'<li><span>{esc(c["name"])}</span><span class="muted">{esc(c["issuer"])}</span></li>' for c in d["creds"]) \
        or '<li class="muted">First credential in progress.</li>'
    bench = "".join(
        f'<li><span><span class="{"check" if b["done"] else "todo"}">{"■" if b["done"] else "□"}</span> {esc(b["text"])}</span>'
        f'<span class="muted">{esc(b["section"].split("—")[0].strip())}</span></li>'
        for b in d["benchmarks"] if b["done"] or b["section"].startswith(f"Stage {st['stage']}"))
    projects = "".join(
        '<div class="card">'
        f'<h3>{esc(pr["name"])}</h3><div class="muted">{esc(pr["status"])}</div><p>{esc(pr["summary"])}</p>'
        + (f'<a href="{esc(pr["github"])}">Repository →</a>' if pr["github"] else "")
        + (f'<img src="{esc(pr["plot"])}" alt="Plot for {esc(pr["name"])}">' if pr["plot"] else "")
        + '<div class="tags">' + "".join(f"<span>{esc(s)}</span>" for s in pr["skills"]) + "</div></div>"
        for pr in d["projects"]) or '<p class="muted">Projects appear here as they ship.</p>'
    essays = "".join(f'<li><a href="essays/{e["slug"]}.html">{esc(e["title"])}</a><span class="muted">{esc(e["date"])} · {e["words"]} words</span></li>'
                     for e in d["essays"]) or '<li class="muted">Essays appear here once published (<code>status: published</code>).</li>'
    skills = "".join(f"<span>{esc(s['name'])} · {esc(s.get('level', ''))}</span>" for s in d["skills"])
    courses = "".join(f"<li><span>{esc(c['text'])}</span></li>" for c in d["courses"])
    engine = d["engine_url"] or "https://github.com/"
    clone = engine.rstrip("/") + ".git" if "github.com/" in engine and engine.count("/") >= 4 else engine
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(p['name'])} — Portfolio</title>
<meta name="description" content="{esc(p.get('label', ''))}">
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="hero"><div>
<h1>{esc(p['name'])}</h1><div class="label">{esc(p.get('label', ''))}</div>
<div class="links">{''.join(links)}</div></div>
<div class="badge">Stage {st['stage']} · {esc(d['stage'].get('name', ''))}</div></header>
<p class="summary">{esc(p.get('summary', ''))}</p>

<h2>At a glance</h2>
<div class="stats">
<div class="stat"><b>{total_h:.0f}</b><span>study hours logged</span></div>
<div class="stat"><b>{sum(1 for b in d['benchmarks'] if b['done'])}</b><span>benchmarks passed</span></div>
<div class="stat"><b>{len(d['creds'])}</b><span>credentials</span></div>
<div class="stat"><b>{len(d['projects'])}</b><span>projects</span></div>
<div class="stat"><b>{len(d['essays'])}</b><span>essays published</span></div>
<div class="stat"><b>{st['streak_days']}</b><span>day streak</span></div>
</div>
<div class="heat-wrap"><h2>Last 16 weeks</h2>{heatmap(st)}</div>

<h2>Curriculum progress — {esc(st['curriculum_name'])}</h2>
{bars}

<h2>Verified credentials & coursework</h2>
<ul class="clean">{creds}{courses}</ul>

<h2>Skills</h2><div class="tags">{skills or '<span>Building foundations</span>'}</div>

<h2>Shipped code & data analyses</h2>
<div class="grid2">{projects}</div>

<h2>Essays & research</h2>
<ul class="clean">{essays}</ul>

<h2>Benchmarks</h2>
<ul class="clean">{bench}</ul>

<section class="cta" id="praxis">
<h2>Try the engine: download Praxis OS</h2>
<p><strong>This résumé wrote itself.</strong> Every number above is generated by <em>Praxis: The Emergent Grid</em> — a Godot automation game
where I program a research drone in real Python. Drone code runs against real datasets and is committed to git; study sessions recharge the
drone's Cognitive Bandwidth; passing a curriculum benchmark unlocks new sensors in the tech tree and recompiles this page.</p>
<p>The engine is open source and curriculum-agnostic. Swap in your own degree or self-study roadmap and gamify it.</p>
<pre>git clone {esc(clone)} ~/Learning
cd ~/Learning && pip3 install -r _scripts/requirements.txt
python3 _scripts/learn.py init-curriculum --list
python3 _scripts/learn.py game</pre>
<a class="btn" href="{esc(engine)}">Get praxis-engine on GitHub</a>
<a class="btn ghost" href="{esc(engine.rstrip('/'))}/archive/refs/heads/main.zip">Download .zip</a>
</section>

<footer>Generated {C.now().strftime('%Y-%m-%d %H:%M')} by Praxis · <a href="resume.json">resume.json</a>
{' · <a href="resume.pdf">PDF</a>' if OUT_PDF.exists() else ''}</footer>
</div></body></html>
"""


def render_essay(e: dict, profile: dict) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(e['title'])} — {esc(profile['name'])}</title><style>{CSS}</style></head>
<body><div class="wrap"><p class="no-print"><a href="../index.html">← {esc(profile['name'])}</a></p>
<article class="essay"><h1>{esc(e['title'])}</h1><p class="muted">{esc(e['date'])} · {e['words']} words</p>
{md_to_html(re.sub(r'^# .*$', '', e['body'], count=1, flags=re.M))}</article></div></body></html>
"""


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def typst_source(rj: dict) -> str:
    def t(s) -> str:
        return str(s or "").replace("\\", "\\\\").replace("#", "\\#").replace("$", "\\$").replace("@", "\\@") \
            .replace("*", "\\*").replace("_", "\\_").replace("<", "\\<").replace("[", "\\[").replace("]", "\\]")
    b = rj["basics"]
    lines = ['#set page(margin: 1.6cm)', '#set text(font: ("Iowan Old Style", "Palatino", "Georgia", "Linux Libertine"), size: 10.5pt)',
             f'#align(center)[#text(20pt, weight: "bold")[{t(b["name"])}] \\ #text(11pt)[{t(b["label"])}]]',
             f'#par(justify: true)[{t(b["summary"])}]']

    def section(title, rows):
        if rows:
            lines.append(f'== {t(title)}')
            lines.extend(f"- {r}" for r in rows)
    ed = rj["education"][0]
    section("Education", [f'*{t(ed["institution"])}* — {t(ed["area"])}, {t(ed["studyType"])} ({t(ed["score"])})']
            + [t(c) for c in ed["courses"]])
    section("Certificates", [f'{t(c["name"])} — {t(c["issuer"])}' for c in rj["certificates"]])
    section("Projects", [f'*{t(p["name"])}*: {t(p["description"])}' for p in rj["projects"]])
    section("Writing", [f'{t(p["name"])} ({t(p["releaseDate"])})' for p in rj["publications"]])
    section("Skills", [", ".join(t(s["name"]) for s in rj["skills"])] if rj["skills"] else [])
    return "\n".join(lines) + "\n"


def compile_pdf(rj: dict) -> str | None:
    if shutil.which("typst"):
        src = C.PORTFOLIO / ".resume.typ"
        src.write_text(typst_source(rj), encoding="utf-8")
        r = subprocess.run(["typst", "compile", str(src), str(OUT_PDF)], capture_output=True, text=True)
        src.unlink(missing_ok=True)
        if r.returncode == 0:
            return "typst"
    try:
        from weasyprint import HTML  # type: ignore

        HTML(filename=str(OUT_HTML)).write_pdf(str(OUT_PDF))
        return "weasyprint"
    except Exception:
        pass
    if shutil.which("wkhtmltopdf"):
        if subprocess.run(["wkhtmltopdf", "-q", str(OUT_HTML), str(OUT_PDF)], capture_output=True).returncode == 0:
            return "wkhtmltopdf"
    for chrome in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome"),
                   shutil.which("chromium"), shutil.which("chromium-browser")):
        if chrome and Path(chrome).exists():
            r = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox", f"--print-to-pdf={OUT_PDF}",
                                "--no-pdf-header-footer", OUT_HTML.as_uri()], capture_output=True, timeout=60)
            if r.returncode == 0 and OUT_PDF.exists():
                return "chrome"
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page()
            pg.goto(OUT_HTML.as_uri())
            pg.pdf(path=str(OUT_PDF), format="Letter", print_background=False)
            br.close()
        return "playwright"
    except Exception:
        return None


# --------------------------------------------------------------------------


def build(pdf: bool = True) -> dict:
    d = collect()
    rj = resume_json(d)
    C.PORTFOLIO.mkdir(parents=True, exist_ok=True)
    C.atomic_write(OUT_JSON, json.dumps(rj, indent=2, ensure_ascii=False) + "\n")
    ESSAY_DIR.mkdir(exist_ok=True)
    keep = set()
    for e in d["essays"]:
        f = ESSAY_DIR / f"{e['slug']}.html"
        C.atomic_write(f, render_essay(e, d["profile"]))
        keep.add(f.name)
    for f in ESSAY_DIR.glob("*.html"):
        if f.name not in keep:
            f.unlink()
    C.atomic_write(OUT_HTML, render_html(d, rj))
    engine = None
    if pdf:
        engine = compile_pdf(rj)
        if engine:
            C.atomic_write(OUT_HTML, render_html(d, rj))  # add the PDF link
    return {"ok": True, "resume_json": C.rel(OUT_JSON), "index_html": C.rel(OUT_HTML),
            "pdf": C.rel(OUT_PDF) if engine else None, "pdf_engine": engine,
            "projects": len(d["projects"]), "essays": len(d["essays"]), "credentials": len(d["creds"]),
            "message": f"Portfolio rebuilt → {C.rel(OUT_HTML)}" + (f" + PDF ({engine})" if engine else
                       (" (no PDF tool found: brew install typst)" if pdf else ""))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--open", action="store_true", help="open index.html in the browser")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(argv)
    res = build(pdf=not a.no_pdf)
    if a.open and not a.headless:
        res["opened"] = C.open_target(OUT_HTML.as_uri())
    C.emit(res, a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
