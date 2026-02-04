# Plan: Source Reliability Graph (Option A)

Date: 2026-02-03
Owner: Codex

## Goal
Build an in‑memory source reliability graph that records fallback transitions and successes, and compute a ranking (power‑method) that can later be used to improve source ordering.

## Acceptance Criteria
- A `SourceReliabilityGraph` exists and records:
  - Self‑loop on success.
  - Fallback transitions from failed/empty source to next attempted source.
- Graph can compute a stable rank vector via power iteration.
- Graph snapshot and ranks are accessible from `SourceManager` (health report or explicit getter).
- No changes to public search results or behavior unless explicitly enabled.

## Dependencies
- None external. Use only stdlib.

## Files To Touch
- `sources/source_graph.py` (new): graph structure, record methods, power iteration.
- `sources/__init__.py`: instantiate graph, record transitions, expose graph report.
- `tests/test_source_graph.py` (new): unit tests for ranking behavior.

## Plan
1. Implement `SourceReliabilityGraph` with:
   - `add_node`, `record_success`, `record_fallback`, `snapshot`, `compute_ranks`.
   - Thread‑safe updates.
2. Wire graph into `SourceManager`:
   - Instantiate graph after sources discovered.
   - Record success in `_record_success`.
   - Record fallback edges in `_with_fallback` when moving to the next source after empty/failure.
3. Expose graph report:
   - Add `get_source_graph_report()` or include in `get_health_report()` (admin‑only endpoint already uses it).
4. Add tests for graph ranking (power method):
   - Asymmetric transition graph ranks target higher.
   - Sink handling doesn’t crash and returns normalized scores.

## Test Plan
- `pytest tests/test_source_graph.py`

## Stop Conditions
- Unclear whether graph ranking should affect ordering immediately.
- Any change that would alter request behavior without explicit opt‑in.
