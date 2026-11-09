"""Challenge 5 — Schelling Segregation ABM (Stage 3) → benchmark s3_abm

A 10x10 city of two groups (1 and 2) with a few empty homes.
Write the rule each agent uses to decide whether it is unhappy and moves:

    rule(my_group, neighbor_groups) -> True if unhappy

Then step the model with run_abm_step(rule) and watch what emerges.
Pass: the segregation index rises by at least 0.15 — even though no agent
wants a segregated city. Afterwards, write up *why* in 04 Writing/.

Useful API: run_abm_step(rule), abm_grid(), log(...), submit_result(...).
"""
from station_api import log, run_abm_step, submit_result

THRESHOLD = 0.3  # "I'm fine as long as 30% of my neighbours are like me"


def rule(my_group, neighbor_groups):
    """Your turn: return True when fewer than THRESHOLD of the neighbours
    share my_group. An agent with no neighbours is content."""
    return False


history = []
for step in range(20):
    result = run_abm_step(rule)
    history.append(result["segregation"])
    if result["moved"] == 0:
        log(f"Equilibrium after {step + 1} steps")
        break

submit_result(segregation=history)
