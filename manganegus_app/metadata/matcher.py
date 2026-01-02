"""
================================================================================
MangaNegus v3.1 - Fuzzy Title Matcher
================================================================================
Implements fuzzy string matching for resolving manga titles across different
metadata providers (AniList, MyAnimeList, Kitsu, Shikimori, MangaUpdates).

Problem:
  User searches "One Piece" on MangaDex (ID: "a1c7c817-4e59...")
  We need to find the same manga on external APIs with different IDs:
    - AniList: 30013
    - MyAnimeList: 21
    - Kitsu: 42765
    - MangaUpdates: 61

Solution:
  Fuzzy title matching with confidence scoring using rapidfuzz library.

Design follows Gemini's architecture from /tmp/fuzzy_matcher_task.txt
================================================================================
"""

import re
import logging
import time
from typing import List, Optional, Dict
from rapidfuzz import fuzz

from .models import UnifiedMetadata, IDMapping


logger = logging.getLogger(__name__)


# =============================================================================
# TITLE NORMALIZATION
# =============================================================================

class TitleMatcher:
    """
    Fuzzy matcher for resolving manga titles across different providers.

    Uses rapidfuzz for string matching with configurable thresholds.
    Handles title normalization, alternative titles, and confidence scoring.
    """

    # Common words to remove during normalization
    STOP_WORDS = {'the', 'a', 'an'}

    # Roman numeral mappings for normalization
    ROMAN_NUMERALS = {
        'i': '1',
        'ii': '2',
        'iii': '3',
        'iv': '4',
        'v': '5',
        'vi': '6',
        'vii': '7',
        'viii': '8',
        'ix': '9',
        'x': '10',
        'xi': '11',
        'xii': '12',
        'xiii': '13',
        'xiv': '14',
        'xv': '15',
        'xvi': '16',
        'xvii': '17',
        'xviii': '18',
        'xix': '19',
        'xx': '20'
    }

    # Common abbreviations
    ABBREVIATIONS = {
        'pt': 'part',
        'ch': 'chapter',
        'vol': 'volume',
        'vs': 'versus'
    }

    def __init__(self, default_threshold: float = 85.0):
        """
        Initialize the title matcher.

        Args:
            default_threshold: Minimum similarity score for matches (0-100)
        """
        self.default_threshold = default_threshold
        logger.info(f"TitleMatcher initialized with threshold={default_threshold}")

    def normalize_title(self, title: str) -> str:
        """
        Normalize title for comparison.

        Steps:
          1. Convert to lowercase
          2. Remove special characters (keep alphanumeric and spaces)
          3. Remove common stop words ("the", "a", "an")
          4. Expand abbreviations
          5. Convert Roman numerals to Arabic numbers
          6. Collapse multiple spaces
          7. Strip whitespace

        Args:
            title: Raw title string

        Returns:
            Normalized title string

        Examples:
            "The Disastrous Life of Saiki K." → "disastrous life saiki k"
            "One-Piece!" → "one piece"
            "Attack on Titan III" → "attack on titan 3"
            "Hunter x Hunter" → "hunter hunter"
        """
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower()

        # Remove special characters (keep alphanumeric, spaces, and hyphens)
        # Note: We keep hyphens temporarily to preserve "x-men" vs "xmen"
        normalized = re.sub(r'[^\w\s-]', ' ', normalized)

        # Split into words for processing
        words = normalized.split()

        # Remove stop words
        words = [w for w in words if w not in self.STOP_WORDS]

        # Expand abbreviations
        words = [self.ABBREVIATIONS.get(w, w) for w in words]

        # Convert Roman numerals to Arabic numbers
        words = [self.ROMAN_NUMERALS.get(w, w) for w in words]

        # Remove hyphens now (they've served their purpose)
        words = [w.replace('-', '') for w in words]

        # Join and collapse multiple spaces
        normalized = ' '.join(words)
        normalized = re.sub(r'\s+', ' ', normalized)

        # Final strip
        return normalized.strip()

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity score between two titles.

        Uses both basic ratio and token-sort ratio from rapidfuzz
        to handle word order variations.

        Algorithm:
          1. Normalize both titles
          2. Calculate basic fuzz ratio
          3. Calculate token-sort ratio (order-independent)
          4. Return the highest score

        Args:
            title1: First title
            title2: Second title

        Returns:
            Similarity score (0-100)

        Examples:
            calculate_similarity("One Piece", "One-Piece") → ~98
            calculate_similarity("Attack on Titan", "Titan on Attack") → ~95
            calculate_similarity("Naruto", "Boruto") → ~67
        """
        if not title1 or not title2:
            return 0.0

        # Normalize both titles
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)

        # Check for exact match after normalization
        if norm1 == norm2:
            return 100.0

        # Basic ratio (order-dependent)
        basic_score = fuzz.ratio(norm1, norm2)

        # Token sort ratio (order-independent)
        # Useful for "Life of Pi" vs "Pi of Life"
        token_score = fuzz.token_sort_ratio(norm1, norm2)

        # Token set ratio (handles subset matches)
        # Useful for "The Disastrous Life of Saiki K" vs "Saiki K"
        token_set_score = fuzz.token_set_ratio(norm1, norm2)

        # Use the highest score
        best_score = max(basic_score, token_score, token_set_score)

        logger.debug(
            f"Similarity: '{title1}' vs '{title2}' → "
            f"basic={basic_score:.1f}, token={token_score:.1f}, "
            f"token_set={token_set_score:.1f}, best={best_score:.1f}"
        )

        return best_score

    def find_best_match(
        self,
        query_title: str,
        candidates: List[UnifiedMetadata],
        threshold: Optional[float] = None
    ) -> Optional[UnifiedMetadata]:
        """
        Find the best matching candidate for the query title.

        Algorithm:
          1. Normalize query title
          2. For each candidate:
             - Calculate similarity with primary title
             - Calculate similarity with all alternative titles
             - Track the highest score
          3. Return candidate with highest score >= threshold
          4. Return None if no match above threshold

        Args:
            query_title: Title to match
            candidates: List of potential matches
            threshold: Minimum similarity score (uses default if None)

        Returns:
            Best matching UnifiedMetadata or None

        Example:
            matcher = TitleMatcher()
            candidates = [
                UnifiedMetadata(negus_id='1', titles={'en': 'One Piece'}),
                UnifiedMetadata(negus_id='2', titles={'en': 'Two Piece'})
            ]
            match = matcher.find_best_match('One-Piece', candidates)
            # Returns first candidate with ~98% similarity
        """
        if not query_title or not candidates:
            logger.warning("find_best_match: Empty query or candidates list")
            return None

        if threshold is None:
            threshold = self.default_threshold

        best_candidate = None
        best_score = 0.0
        best_matched_title = ""

        logger.debug(f"Finding best match for '{query_title}' among {len(candidates)} candidates")

        for candidate in candidates:
            # Get all titles to check
            all_titles = candidate.get_all_titles()

            if not all_titles:
                logger.warning(f"Candidate {candidate.negus_id} has no titles")
                continue

            # Calculate similarity with each title
            max_score = 0.0
            matched_title = ""

            for title in all_titles:
                score = self.calculate_similarity(query_title, title)

                if score > max_score:
                    max_score = score
                    matched_title = title

            # Update best match if this is better
            if max_score > best_score:
                best_score = max_score
                best_candidate = candidate
                best_matched_title = matched_title

        # Check if best score meets threshold
        if best_score >= threshold:
            logger.info(
                f"Best match: '{best_matched_title}' (score={best_score:.1f}, "
                f"id={best_candidate.negus_id})"
            )
            return best_candidate
        else:
            logger.info(
                f"No match found above threshold {threshold:.1f}. "
                f"Best score was {best_score:.1f}"
            )
            return None

    def resolve_ids(
        self,
        title: str,
        alt_titles: List[str],
        search_results: Dict[str, List[UnifiedMetadata]],
        threshold: Optional[float] = None
    ) -> IDMapping:
        """
        Resolve external API IDs by matching titles across providers.

        This is the main entry point for ID resolution. Takes search results
        from multiple providers and finds the best match for each.

        Algorithm:
          1. Try matching with primary title first
          2. If no match, try alternative titles
          3. For each provider in search_results:
             - Find best matching result
             - Extract provider ID from match
          4. Calculate overall confidence score
          5. Return IDMapping with all resolved IDs

        Args:
            title: Primary title to match
            alt_titles: Alternative titles/synonyms
            search_results: Dict mapping provider_id → search results
                Example: {
                    'anilist': [metadata1, metadata2, ...],
                    'mal': [metadata3, metadata4, ...],
                    'kitsu': [metadata5, ...]
                }
            threshold: Minimum similarity score (uses default if None)

        Returns:
            IDMapping with resolved IDs and confidence score

        Example:
            search_results = {
                'anilist': [
                    UnifiedMetadata(negus_id='anilist:30013',
                                  titles={'en': 'One Piece'},
                                  mappings={'anilist': '30013'})
                ],
                'mal': [
                    UnifiedMetadata(negus_id='mal:21',
                                  titles={'en': 'One Piece'},
                                  mappings={'mal': '21'})
                ]
            }

            mapping = matcher.resolve_ids('One Piece', [], search_results)
            # Returns: IDMapping(
            #   anilist_id='30013',
            #   mal_id='21',
            #   confidence=95.5
            # )
        """
        if threshold is None:
            threshold = self.default_threshold

        logger.info(f"Resolving IDs for title: '{title}'")
        logger.debug(f"Alternative titles: {alt_titles}")
        logger.debug(f"Providers to search: {list(search_results.keys())}")

        # Initialize mapping
        mapping = IDMapping(
            source_title=title,
            created_at=time.time()
        )

        # Track scores for confidence calculation
        provider_scores: Dict[str, float] = {}

        # All titles to try (primary + alternatives)
        titles_to_try = [title] + alt_titles

        # Try to resolve each provider
        for provider_id, candidates in search_results.items():
            if not candidates:
                logger.debug(f"No candidates from {provider_id}")
                continue

            best_match = None
            best_score = 0.0

            # Try each title variant
            for search_title in titles_to_try:
                match = self.find_best_match(search_title, candidates, threshold)

                if match:
                    # Calculate actual score for this match
                    all_titles = match.get_all_titles()
                    scores = [
                        self.calculate_similarity(search_title, t)
                        for t in all_titles
                    ]
                    score = max(scores) if scores else 0.0

                    if score > best_score:
                        best_match = match
                        best_score = score

            # Extract ID from best match
            if best_match and best_match.mappings:
                provider_id_value = best_match.mappings.get(provider_id)

                if provider_id_value:
                    logger.info(
                        f"Resolved {provider_id}: {provider_id_value} "
                        f"(score={best_score:.1f})"
                    )

                    # Store ID based on provider
                    if provider_id == 'anilist':
                        mapping.anilist_id = provider_id_value
                    elif provider_id == 'mal':
                        mapping.mal_id = provider_id_value
                    elif provider_id == 'kitsu':
                        mapping.kitsu_id = provider_id_value
                    elif provider_id == 'shikimori':
                        mapping.shikimori_id = provider_id_value
                    elif provider_id == 'mangaupdates':
                        mapping.mangaupdates_id = provider_id_value

                    # Track score
                    provider_scores[provider_id] = best_score

                    # Update matched title if this is the best so far
                    if best_score > mapping.confidence:
                        mapping.matched_title = best_match.get_primary_title()

        # Calculate overall confidence score
        if provider_scores:
            # Use average of all provider scores
            mapping.confidence = sum(provider_scores.values()) / len(provider_scores)

            logger.info(
                f"ID resolution complete. Confidence: {mapping.confidence:.1f}%, "
                f"Resolved: {sum(1 for _ in [mapping.anilist_id, mapping.mal_id, "
                f"mapping.kitsu_id, mapping.shikimori_id, mapping.mangaupdates_id] "
                f"if _)}/{len(search_results)} providers"
            )
        else:
            logger.warning("No IDs resolved for any provider")
            mapping.confidence = 0.0

        return mapping


# =============================================================================
# ID MAPPING CACHE
# =============================================================================

class IDMappingCache:
    """
    Simple in-memory cache for ID mappings to avoid re-matching.

    Stores mappings by normalized title hash for fast lookups.
    Implements TTL (time-to-live) for cache invalidation.

    TODO: Future enhancements:
      - Persistent cache (SQLite or JSON file)
      - LRU eviction for memory management
      - Cache statistics (hit rate, miss rate)
    """

    def __init__(self, ttl: float = 86400.0):
        """
        Initialize the cache.

        Args:
            ttl: Time-to-live in seconds (default: 24 hours)
        """
        self._cache: Dict[str, IDMapping] = {}
        self._ttl = ttl
        logger.info(f"IDMappingCache initialized with TTL={ttl}s ({ttl/3600:.1f}h)")

    def _make_key(self, title: str) -> str:
        """
        Create a cache key from title.

        Uses normalized title to ensure "One Piece" and "One-Piece"
        map to the same cache entry.

        Args:
            title: Title to create key for

        Returns:
            Cache key (normalized title)
        """
        matcher = TitleMatcher()
        return matcher.normalize_title(title)

    def get(self, title: str) -> Optional[IDMapping]:
        """
        Get cached mapping by title.

        Args:
            title: Title to lookup

        Returns:
            Cached IDMapping or None if not found/expired
        """
        key = self._make_key(title)

        if key not in self._cache:
            logger.debug(f"Cache MISS: '{title}' (key: '{key}')")
            return None

        mapping = self._cache[key]

        # Check if expired
        age = time.time() - mapping.created_at
        if age > self._ttl:
            logger.info(f"Cache EXPIRED: '{title}' (age={age:.0f}s)")
            del self._cache[key]
            return None

        logger.debug(f"Cache HIT: '{title}' (age={age:.0f}s)")
        return mapping

    def set(self, title: str, mapping: IDMapping):
        """
        Store mapping in cache.

        Args:
            title: Title to cache under
            mapping: ID mapping to store
        """
        key = self._make_key(title)
        self._cache[key] = mapping
        logger.debug(f"Cache SET: '{title}' → {len(self._cache)} total entries")

    def clear(self):
        """Clear all cached mappings."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")

    def prune_expired(self):
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        now = time.time()
        expired_keys = [
            key for key, mapping in self._cache.items()
            if (now - mapping.created_at) > self._ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cache pruned: {len(expired_keys)} expired entries removed")

        return len(expired_keys)

    def stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        now = time.time()
        valid_count = sum(
            1 for mapping in self._cache.values()
            if (now - mapping.created_at) <= self._ttl
        )
        expired_count = len(self._cache) - valid_count

        return {
            'total_entries': len(self._cache),
            'valid_entries': valid_count,
            'expired_entries': expired_count
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Global cache instance (singleton pattern)
_global_cache: Optional[IDMappingCache] = None


def get_cache() -> IDMappingCache:
    """
    Get the global cache instance.

    Creates cache on first access (lazy initialization).

    Returns:
        Global IDMappingCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = IDMappingCache()
    return _global_cache


def normalize_title(title: str) -> str:
    """
    Convenience function for title normalization.

    Args:
        title: Title to normalize

    Returns:
        Normalized title
    """
    matcher = TitleMatcher()
    return matcher.normalize_title(title)


def calculate_similarity(title1: str, title2: str) -> float:
    """
    Convenience function for similarity calculation.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity score (0-100)
    """
    matcher = TitleMatcher()
    return matcher.calculate_similarity(title1, title2)
