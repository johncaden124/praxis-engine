"""Challenge 1 — Sequential & Loops: Survey Sweep (Stage 1)

Goal: sample every respondent on the 5x5 survey field.
The drone starts at (0, 0) in the bottom-left corner.

This one is a worked example so you can see the whole loop work.
Try rewriting it with a single `while` loop, or make it cheaper.
"""
from station_api import move, harvest_data, world_size, log

width, height = world_size()
samples = []

for row in range(height):
    for step in range(width):
        samples.append(harvest_data())
        if step < width - 1:
            # boustrophedon ("ox-turning") sweep: east on even rows, west on odd rows
            move("E" if row % 2 == 0 else "W")
    if row < height - 1:
        move("N")

log(f"Collected {len(samples)} samples, mean = {sum(samples) / len(samples):.2f}")
