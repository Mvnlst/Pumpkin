import random
import math


# Generate a test instance
# n: amount of nodes
# k: amount of outgoing edges for each node
# seed: seed to generate identical test instances 
def generate_instance(n, k, seed=None):
    rng = random.Random(seed)

    # Generate positions in a square of 1 by 1
    positions = {}
    for i in range(n):
        x = rng.random()
        y = rng.random()
        positions[i] = (x, y)

    # Compute distances
    def distance(i, j):
        return math.dist(positions[i], positions[j])

    # Build edges
    edges = {}
    for i in range(n):
        edges[i] = set()

        # Compute all distances to other nodes
        distances = []
        for j in range(n):
            if i != j:
                distances.append((j, distance(i, j)))

        # Sort by distance
        distances.sort(key=lambda x: x[1])

        # Take k nearest neighbours
        for (node_index, d) in distances[:k]:
            edges[i].add(node_index)

    # Now perform a random walk to ensure there is a Hamiltonian cycle
    visited = set()
    order = []
    # Randomly select starting node
    current = rng.randrange(n)
    visited.add(current)
    order.append(current)

    while len(visited) < n:
        neighbours = list(edges[current])

        # Find neighbours not yet visited
        unvisited = [node for node in edges[current] if node not in visited]

        # If at least one neighbour is not visited yet,
        if len(unvisited) > 0:
            # Choose one at random.
            nxt = rng.choice(unvisited)
        else:
            # Else, choose another non-neighbouring node at random
            remaining = [node for node in range(n) if node not in visited]
            nxt = rng.choice(remaining)
            # And create an edge from the current node to that node
            edges[current].add(nxt)

        visited.add(nxt)
        order.append(nxt)
        current = nxt

    # Close the cycle by adding an edge from last node to the starting one
    edges[current].add(order[0])

    return edges, order, count_strong_bridges(edges)

def count_strong_bridges(edges):
    n = len(edges)
    strong_bridges = []

    for u in range(n):
        if len(edges[u]) <= 1: continue
        for v in list(edges[u]):
            reachable = reachable_without_edge(edges, u, v)

            if not reachable:
                strong_bridges.append((u + 1, v + 1))

    return strong_bridges

def reachable_without_edge(edges, start, target):
    n = len(edges)
    visited = [False] * n
    stack = [start]

    while stack:
        u = stack.pop()

        if visited[u]:
            continue

        visited[u] = True

        if u == target:
            return True

        for v in edges[u]:

            # skip the tested edge
            if u == start and v == target:
                continue

            if not visited[v]:
                stack.append(v)

    return False

