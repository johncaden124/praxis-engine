---
type: review
kind: <% await tp.system.suggester(["weekly", "quarterly"], ["weekly", "quarterly"]) %>
date: <% tp.date.now("YYYY-MM-DD") %>
tags: [review, private]
---

# Review — <% tp.date.now("YYYY-MM-DD") %>

## Hours vs. floor (13–18h)

```dataview
TABLE hours, track, pages FROM "02 Today" WHERE file.day >= date(today) - dur(6 days) SORT file.name ASC
```

## What I finished

## What I avoided, and why

## Benchmark progress

## People: who did I listen to?

## Next week's one change
