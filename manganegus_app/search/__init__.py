"""
================================================================================
MangaNegus v3.1 - Smart Search Package
================================================================================
Intelligent search with deduplication and metadata enrichment.

Components:
  - deduplicator.py - Groups duplicate manga from different sources
  - smart_search.py - Orchestrates parallel queries and enrichment
  - cache.py - Search result caching (1 hour TTL) [TODO]

Design:
  - Parallel queries to top 5 sources
  - Fuzzy title matching for deduplication (85% threshold)
  - Metadata enrichment from external APIs
  - Redis-backed caching for performance [TODO]
================================================================================
"""

from .deduplicator import SearchDeduplicator, UnifiedSearchResult
from .smart_search import SmartSearch

# MangaResult is from sources.base, not defined here
__all__ = ['SearchDeduplicator', 'UnifiedSearchResult', 'SmartSearch']
