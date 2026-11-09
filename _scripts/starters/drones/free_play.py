"""Free play on the sandbox grid (size grows as you unlock Tech Tree nodes).

Harvest respondents, clean corrupt samples, and see what you find.
Run with challenge id "free" (no pass condition).
"""
from station_api import clean_outlier, harvest_data, log, move, scan, world_size

w, h = world_size()
total = 0
for row in range(h):
    for _ in range(w):
        tile = scan()
        if tile.get("corrupt"):
            clean_outlier()
        if tile.get("type") == "respondent":
            total += harvest_data() or 0
        move("E" if row % 2 == 0 else "W")
    move("N")
log(f"Total signal harvested: {total:.1f}")
