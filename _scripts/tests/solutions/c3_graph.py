"""Reference solution for c3_graph (used by the test-suite)."""
from collections import deque

from station_api import get_pos, graph, harvest_data, is_wall, move, node_pos, submit_result


def bfs_counts(g, s):
    dist, sigma, q = {s: 0}, {s: 1}, deque([s])
    while q:
        v = q.popleft()
        for w in g[v]:
            if w not in dist:
                dist[w], sigma[w] = dist[v] + 1, 0
                q.append(w)
            if dist[w] == dist[v] + 1:
                sigma[w] += sigma[v]
    return dist, sigma


def betweenness(g):
    info = {v: bfs_counts(g, v) for v in g}
    score = {v: 0.0 for v in g}
    nodes = list(g)
    for i, s in enumerate(nodes):
        ds, ss = info[s]
        for t in nodes[i + 1:]:
            for v in g:
                if v in (s, t):
                    continue
                dv, sv = info[v]
                if ds[v] + dv[t] == ds[t]:
                    score[v] += ss[v] * sv[t] / ss[t]
    return score


def grid_path(start, goal):
    prev, q = {start: None}, deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for d, (dx, dy) in {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}.items():
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt not in prev and not is_wall(*nxt):
                prev[nxt] = (cur, d)
                q.append(nxt)
    path, cur = [], goal
    while prev[cur] is not None:
        cur, d = prev[cur]
        path.append(d)
    return path[::-1]


g = graph()
sc = betweenness(g)
broker = max(sc, key=sc.get)
for d in grid_path(get_pos(), node_pos(broker)):
    move(d)
harvest_data()
submit_result(node=broker)
