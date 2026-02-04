# Algorithm Findings for MangaNegus

Date: 2026-02-03

## Summary
The slow areas reported (source loading, search, downloads, page load, manga grid) map best to algorithms that reduce candidate comparisons, prioritize sources under uncertainty, and reduce rendering/IO work. Dijkstra does not fit current flows, but graph-based ranking could later use the power method once a graph is defined.

## Candidate Algorithms Mapped to Code Areas

1. Search deduplication (slow on large result sets)
- Algorithm: MinHash + LSH (shingling + sketching + bucketed candidate generation)
- Why: Replace O(n^2) fuzzy comparisons with fast candidate filtering using hash buckets.
- Primary files: `manganegus_app/search/deduplicator.py`, `manganegus_app/search/smart_search.py`
- Sources:
  - Broder 1997 (“On the resemblance and containment of documents”) for MinHash/sketching
  - Gionis/Indyk/Motwani 1999 for LSH similarity search

2. Source loading / selection order (slow or unreliable sources)
- Algorithm: UCB1 (multi‑armed bandit) to choose which sources to query first
- Why: Dynamically balances exploration vs. exploitation using observed success + latency
- Primary files: `sources/__init__.py`, `manganegus_app/search/smart_search.py`
- Source:
  - Auer/Cesa‑Bianchi/Fischer 2002 (finite‑time analysis of multi‑armed bandits)

3. Cache hit rate under mixed workloads
- Algorithm: ARC (Adaptive Replacement Cache)
- Why: Auto‑balances recency vs frequency, better for shifting access patterns
- Primary files: `sources/__init__.py`, `manganegus_app/search/cache.py`
- Source:
  - Megiddo/Modha 2003 (ARC)

4. Rate limiting for downloads + source requests
- Algorithm: Token‑bucket rate limiting
- Why: Allows bursts while enforcing long‑term rate caps to avoid bans/timeouts
- Primary files: `sources/base.py`, `sources/__init__.py`, `manganegus_app/tasks/downloads.py`
- Source:
  - RFC 2697

5. Webpage + manga card grid load time
- Algorithm: List virtualization (windowing)
- Why: Only render visible cards; reduce DOM size and layout cost
- Primary files: `static/js/*`, `templates/index.html`, `static/css/styles.css`
- Source:
  - web.dev “Virtualize large lists with react-window” (concept generalizes to vanilla JS)

6. Image loading for cards
- Algorithm: Intersection Observer for lazy loading
- Why: Efficient visibility detection without scroll polling
- Primary files: `static/js/*`
- Source:
  - W3C Intersection Observer spec

## Power Method (Where It Fits)
- The power method finds the dominant eigenvector of a matrix; it is useful for ranking in graph systems (e.g., PageRank‑style centrality).
- Current code does not define a graph structure suitable for power iteration.
- If we build a graph (see next section), power method can compute source/manga “importance” or reliability ranking.

## Graph Build Options (For Future Ranking)
Option A: Source Reliability Graph
- Nodes: sources
- Edges: fallback transitions or co‑success on the same query
- Edge weights: (latency, success rate, ban risk)
- Use: compute a global ranking or per‑query routing hints

Option B: Manga Similarity Graph
- Nodes: manga titles
- Edges: similarity (MinHash/LSH or shared metadata)
- Edge weights: similarity distance
- Use: recommendations or “related titles” ranking

## Suggested “Both Methods” to Start With
1) Implement MinHash + LSH for search dedup candidate selection
2) Implement UCB1 for adaptive source ordering

Both directly target the reported slow paths (search and source loading) without changing external behavior.

## References (primary)
- Broder, A. Z. “On the resemblance and containment of documents.” SEQUENCES 1997.
- Gionis, Indyk, Motwani. “Similarity Search in High Dimensions via Hashing.” VLDB 1999.
- Auer, Cesa‑Bianchi, Fischer. “Finite‑time Analysis of the Multiarmed Bandit Problem.” Machine Learning 2002.
- Megiddo, Modha. “ARC: A Self‑Tuning, Low Overhead Replacement Cache.” FAST 2003.
- RFC 2697. “A Single Rate Three Color Marker.” 1999.
- W3C. “Intersection Observer.”
- web.dev. “Virtualize large lists with react-window.”
