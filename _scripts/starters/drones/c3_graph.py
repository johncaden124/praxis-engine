"""Challenge 3 — Weak Ties: Graph Traversal (Stage 2)

Two tight-knit friend groups live in a walled 7x7 neighbourhood.
1. graph() returns the social network as {person: [friends]}.
   Find the person with the highest *betweenness centrality*: the one who
   sits on the most shortest paths between other people (Granovetter's
   "strength of weak ties"). Implement BFS yourself — no networkx.
2. Fly the drone to that person's tile (node_pos(name)) by running BFS on
   the grid around the walls (is_wall(x, y)), then harvest_data() there.
3. submit_result(node=name).

Useful API: graph(), node_pos(name), is_wall(x, y), get_pos(), move(dir),
harvest_data(), log(msg), submit_result(...).
"""
from collections import deque

from station_api import get_pos, graph, harvest_data, is_wall, log, move, node_pos, submit_result


def shortest_path_counts(g, source):
    """BFS from source. Return (dist, sigma): distance to every node and the
    number of shortest paths to it."""
    dist = {source: 0}
    sigma = {source: 1}
    queue = deque([source])
    while queue:
        v = queue.popleft()
        for w in g[v]:
            if w not in dist:
                dist[w] = dist[v] + 1
                sigma[w] = 0
                queue.append(w)
            if dist[w] == dist[v] + 1:
                sigma[w] += sigma[v]
    return dist, sigma


def betweenness(g):
    """Your turn: use shortest_path_counts to score every node.

    A node v gets credit for each pair (s, t) with v on a shortest path:
    sigma_s[v] * sigma_v[t] / sigma_s[t]  when dist_s[v] + dist_v[t] == dist_s[t].
    """
    scores = {v: 0.0 for v in g}
    # Write the double loop over pairs (s, t) here.
    return scores


def grid_path(start, goal):
    """Your turn: BFS over grid tiles, avoiding walls. Return a list of
    directions like ["N", "E", ...] from start to goal."""
    return []


g = graph()
scores = betweenness(g)
broker = max(scores, key=scores.get)
log(f"Highest betweenness: {broker} ({scores[broker]:.1f})")

for d in grid_path(get_pos(), node_pos(broker)):
    move(d)
harvest_data()
submit_result(node=broker)
