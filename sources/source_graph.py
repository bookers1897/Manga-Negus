"""
Source Reliability Graph

Tracks fallback transitions and successes between sources and provides
power-iteration ranking (PageRank-style) to estimate source reliability.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List


class SourceReliabilityGraph:
    """In-memory directed, weighted graph for source reliability."""

    def __init__(self, damping: float = 0.85):
        self._damping = damping
        self._lock = threading.Lock()
        self._nodes: set[str] = set()
        self._edges: Dict[str, Dict[str, float]] = defaultdict(dict)

    def add_node(self, source_id: str) -> None:
        if not source_id:
            return
        with self._lock:
            self._nodes.add(source_id)

    def reset(self) -> None:
        with self._lock:
            self._nodes.clear()
            self._edges.clear()

    def record_success(self, source_id: str, weight: float = 1.0) -> None:
        """Record a successful attempt as a self-loop."""
        if not source_id:
            return
        self._add_edge(source_id, source_id, weight)

    def record_fallback(self, from_id: str, to_id: str, weight: float = 1.0) -> None:
        """Record a fallback transition from one source to another."""
        if not from_id or not to_id:
            return
        self._add_edge(from_id, to_id, weight)

    def snapshot(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Return a copy of nodes and edges for reporting."""
        with self._lock:
            nodes = sorted(self._nodes)
            edges = {src: dict(dsts) for src, dsts in self._edges.items()}
        return {
            "nodes": nodes,
            "edges": edges,
        }

    def compute_ranks(self, max_iter: int = 50, tol: float = 1e-6) -> Dict[str, float]:
        """
        Compute source ranks using power iteration over the transition matrix.

        Returns a dict of {source_id: rank} that sums to ~1.0.
        """
        with self._lock:
            nodes = sorted(self._nodes)
            edges = {src: dict(dsts) for src, dsts in self._edges.items()}

        n = len(nodes)
        if n == 0:
            return {}

        index = {node: i for i, node in enumerate(nodes)}
        rank = [1.0 / n] * n
        damping = self._damping

        for _ in range(max_iter):
            new_rank = [0.0] * n

            # Identify sinks and compute their total rank mass
            sink_total = 0.0
            out_weights: List[float] = [0.0] * n

            for i, node in enumerate(nodes):
                outgoing = edges.get(node)
                if not outgoing:
                    sink_total += rank[i]
                    continue

                total = 0.0
                for w in outgoing.values():
                    if w > 0:
                        total += w
                if total <= 0:
                    sink_total += rank[i]
                else:
                    out_weights[i] = total

            base = (1.0 - damping) / n
            sink_share = damping * sink_total / n

            for i in range(n):
                new_rank[i] = base + sink_share

            for i, node in enumerate(nodes):
                total = out_weights[i]
                if total <= 0:
                    continue
                for dst, w in edges.get(node, {}).items():
                    if w <= 0:
                        continue
                    j = index.get(dst)
                    if j is None:
                        continue
                    new_rank[j] += damping * rank[i] * (w / total)

            diff = sum(abs(new_rank[i] - rank[i]) for i in range(n))
            rank = new_rank
            if diff < tol:
                break

        return {node: rank[index[node]] for node in nodes}

    def _add_edge(self, from_id: str, to_id: str, weight: float) -> None:
        if weight <= 0:
            return
        with self._lock:
            self._nodes.add(from_id)
            self._nodes.add(to_id)
            current = self._edges[from_id].get(to_id, 0.0)
            self._edges[from_id][to_id] = current + weight
