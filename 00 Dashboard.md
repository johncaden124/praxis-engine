---
tags: [dashboard]
cssclasses: [praxis-dashboard]
---

# 🛰️ Praxis Dashboard

> Requires the **Dataview** community plugin (enable *JavaScript queries* in its settings). Everything here is read live from `_scripts/state.json`, `_scripts/schedule.yaml`, and your notes.

## Today

```dataviewjs
const raw = await app.vault.adapter.read("_scripts/state.json");
const s = JSON.parse(raw);
const days = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"];
const today = days[new Date().getDay()];
let block = "—";
try {
  const sched = await app.vault.adapter.read("_scripts/schedule.yaml");
  const sec = sched.split(/\n  (?=\w+:\n)/).find(x => x.trim().startsWith(today + ":"));
  if (sec) block = [...sec.matchAll(/track: (\w+), start: "([\d:]+)", hours: ([\d.]+)/g)].map(m => `${m[1]} @ ${m[2]} (${m[3]}h)`).join(" · ");
} catch (e) {}
dv.table(["", ""], [
  ["Stage", `${s.stage}`],
  ["Planned block", block],
  ["Session running", s.active_session.running ? `✅ ${s.active_session.track} since ${s.active_session.start_timestamp}` : "—"],
  ["Current reading", dv.fileLink(s.current_focus.reading)],
  ["Current course", s.current_focus.course],
  ["Next essay", dv.fileLink(s.current_focus.essay)],
  ["Project", dv.fileLink(s.current_focus.project)],
  ["Cards due", s.weekly_stats.cards_due],
  ["Cognitive Bandwidth", `${s.cognitive_bandwidth} / ${s.max_bandwidth}`],
  ["XP · Streak", `${s.xp} XP · 🔥 ${s.streak_days} days`],
]);
```

## Next essay due

```dataview
TABLE due, status, words
FROM "04 Writing"
WHERE status != "published" AND due
SORT due ASC
LIMIT 3
```

## This week

```dataview
TABLE WITHOUT ID
  sum(rows.hours) AS "Total h",
  sum(rows.hours_coding) AS "Coding",
  sum(rows.hours_math) AS "Math",
  sum(rows.hours_reading) AS "Reading",
  sum(rows.hours_writing) AS "Writing",
  sum(rows.hours_discussion) AS "Discussion",
  sum(rows.pages) AS "Pages"
FROM "02 Today"
WHERE file.day >= date(today) - dur(6 days)
GROUP BY true
```

```dataview
TABLE hours, track, pages
FROM "02 Today"
SORT file.name DESC
LIMIT 7
```

## Open questions (newest 10)

```dataview
TASK
FROM "05 Questions"
WHERE !completed
SORT line DESC
LIMIT 10
```

## People overdue (30+ days)

```dataviewjs
const s = JSON.parse(await app.vault.adapter.read("_scripts/state.json"));
const now = new Date();
const rows = s.people_nodes
  .map(p => [p.name, p.last_contact, Math.floor((now - new Date(p.last_contact)) / 86400000)])
  .filter(r => r[2] >= 30)
  .sort((a, b) => b[2] - a[2]);
if (rows.length) dv.table(["Person", "Last contact", "Days"], rows);
else dv.paragraph("Everyone contacted within 30 days. 🌱");
```

## Current stage checklist

```dataviewjs
const s = JSON.parse(await app.vault.adapter.read("_scripts/state.json"));
const prefix = `s${s.stage}_`;
const bench = dv.page("01 Plan/benchmarks");
if (bench) dv.taskList(bench.file.tasks.where(t => t.text.includes("(`" + prefix)), false);
const gather = dv.page("01 Plan/Gather List");
const heading = `Stage ${s.stage}`;
if (gather) dv.taskList(gather.file.tasks.where(t => t.section && t.section.subpath && (t.section.subpath === heading || t.header?.subpath === heading)), true);
```

## Credentials

```dataview
TASK
FROM "01 Plan/benchmarks"
WHERE contains(text, "cred_")
```
