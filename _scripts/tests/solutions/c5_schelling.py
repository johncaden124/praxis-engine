"""Reference solution for c5_schelling."""
from station_api import run_abm_step, submit_result


def rule(me, nb):
    return bool(nb) and sum(1 for n in nb if n == me) / len(nb) < 0.4


hist = []
for _ in range(25):
    r = run_abm_step(rule)
    hist.append(r["segregation"])
    if r["moved"] == 0:
        break
submit_result(segregation=hist)
