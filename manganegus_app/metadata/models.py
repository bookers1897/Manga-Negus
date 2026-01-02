"""
================================================================================
MangaNegus v3.1 - Metadata Models
================================================================================
Unified metadata models for external API aggregation.

These models represent the merged data from all metadata providers:
  - AniList (GraphQL)
  - MyAnimeList via Jikan (REST)
  - Kitsu (JSON:API)
  - Shikimori (REST)
  - MangaUpdates (REST)

Design follows Gemini's architecture from /tmp/gemini_metadata_design.txt
================================================================================
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class MangaStatus(str, Enum):
    """Publication status across all providers."""
    RELEASING = "releasing"
    FINISHED = "finished"
    HIATUS = "hiatus"
    CANCELLED = "cancelled"
    NOT_YET_RELEASED = "not_yet_released"
    UNKNOWN = "unknown"


class MangaType(str, Enum):
    """Manga type/format."""
    MANGA = "manga"
    MANHWA = "manhwa"
    MANHUA = "manhua"
    NOVEL = "novel"
    ONE_SHOT = "one_shot"
    DOUJINSHI = "doujinshi"


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class ExternalLink:
    """External link to official sites, stores, social media, etc."""
    site: str  # "Official", "Amazon", "Twitter", "BookWalker"
    url: str
    language: Optional[str] = None


@dataclass
class UnifiedMetadata:
    """
    Unified manga metadata merged from all external APIs.

    This is the heart of the MetaForge system - combines data from:
      - AniList (best for IDs and connections)
      - MyAnimeList (best for rank and popularity)
      - Kitsu (good alternative titles)
      - Shikimori (Russian/English focus)
      - MangaUpdates (best for volume/chapter counts)

    Design Philosophy:
      - Merge ratings using weighted average
      - Union genres/tags from all sources
      - Prefer AniList for IDs (most complete mapping)
      - Use highest quality cover image available
    """

    # =========================================================================
    # CORE IDENTIFIERS
    # =========================================================================

    # Internal identifier (could be source_id:source_manga_id or UUID)
    negus_id: str

    # External API IDs for cross-referencing
    mappings: Dict[str, str] = field(default_factory=dict)
    # Example: {'anilist': '30013', 'mal': '21', 'kitsu': '42765'}

    # =========================================================================
    # TITLES
    # =========================================================================

    # Multiple title variants for better search matching
    titles: Dict[str, str] = field(default_factory=dict)
    # Example: {
    #   'en': 'One Piece',
    #   'ja': 'ワンピース',
    #   'romaji': 'One Piece',
    #   'ja_jp': 'ワンピース'
    # }

    # Alternative titles and synonyms (for fuzzy matching)
    alt_titles: List[str] = field(default_factory=list)

    # =========================================================================
    # DESCRIPTIONS
    # =========================================================================

    synopsis: str = ""  # Long description (prefer AniList, fallback to MAL)
    description: str = ""  # Short description

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================

    status: Optional[MangaStatus] = None
    manga_type: Optional[MangaType] = None

    # =========================================================================
    # CONTENT METADATA
    # =========================================================================

    # Genres (standardized across providers)
    genres: List[str] = field(default_factory=list)
    # Example: ["Action", "Adventure", "Comedy"]

    # Tags (nuanced, from AniList)
    tags: List[str] = field(default_factory=list)
    # Example: ["Pirates", "Time Travel", "Overpowered Protagonist"]

    # Themes (from MAL)
    themes: List[str] = field(default_factory=list)
    # Example: ["Military", "Psychological"]

    # Demographics (target audience)
    demographics: List[str] = field(default_factory=list)
    # Example: ["Shounen", "Seinen"]

    # =========================================================================
    # PEOPLE
    # =========================================================================

    author: Optional[str] = None  # Primary author
    artist: Optional[str] = None  # Primary artist

    # Full author/artist list with roles
    authors: List[Dict[str, str]] = field(default_factory=list)
    # Example: [{'name': 'Oda Eiichiro', 'role': 'Story & Art'}]

    # =========================================================================
    # RATINGS & POPULARITY (AGGREGATED)
    # =========================================================================

    # Weighted average rating (0-10 scale)
    rating: float = 0.0

    # Individual source ratings (for transparency)
    rating_anilist: Optional[float] = None  # 0-100, converted to 0-10
    rating_mal: Optional[float] = None      # 0-10
    rating_kitsu: Optional[float] = None    # 0-100, converted to 0-10
    rating_shikimori: Optional[float] = None  # 0-10
    rating_mangaupdates: Optional[float] = None  # 0-10

    # Popularity metrics
    popularity: int = 0  # Combined followers/members count
    popularity_rank: Optional[int] = None  # From MAL

    # Rankings
    rank: Optional[int] = None  # Overall rank (from MAL)

    # Engagement counts
    favorites_count: int = 0  # Total favorites across all platforms
    members_count: int = 0    # MAL members count

    # =========================================================================
    # STRUCTURE
    # =========================================================================

    volumes: Optional[int] = None    # Total volumes (prefer MangaUpdates)
    chapters: Optional[int] = None   # Total chapters (prefer MangaUpdates)

    # =========================================================================
    # MEDIA
    # =========================================================================

    # Cover images (prefer highest quality)
    cover_image: Optional[str] = None        # Best quality available
    cover_image_large: Optional[str] = None
    cover_image_medium: Optional[str] = None

    # Banner image (from AniList)
    banner_image: Optional[str] = None

    # =========================================================================
    # PUBLICATION
    # =========================================================================

    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Serialization
    serialization: Optional[str] = None  # Magazine/platform

    # =========================================================================
    # LINKS
    # =========================================================================

    links: List[ExternalLink] = field(default_factory=list)
    # Official sites, stores, social media

    # =========================================================================
    # METADATA
    # =========================================================================

    # Content flags
    is_adult: bool = False
    is_licensed: bool = False

    # Cache timestamp (for TTL management)
    last_updated: float = 0.0  # Unix timestamp

    # Confidence score for ID mapping (0-100)
    # Used by fuzzy matcher to determine mapping quality
    mapping_confidence: float = 0.0

    # Provider that was primary source for this metadata
    primary_source: str = "unknown"  # "anilist", "mal", "kitsu", etc.
    source_priority: int = 5  # Priority when merging (1=highest, 5=lowest)

    def get_primary_title(self) -> str:
        """Get the best title for display."""
        if 'en' in self.titles:
            return self.titles['en']
        elif 'romaji' in self.titles:
            return self.titles['romaji']
        elif self.titles:
            return list(self.titles.values())[0]
        return "Unknown"

    def get_all_titles(self) -> List[str]:
        """Get all titles including alternatives for fuzzy matching."""
        all_titles = list(self.titles.values()) + self.alt_titles
        return [t for t in all_titles if t]  # Remove empty strings

    def merge_ratings(self) -> float:
        """
        Calculate weighted average rating from all sources.

        Weights (based on data quality and sample size):
          - MAL: 0.4 (largest user base, most reliable)
          - AniList: 0.3 (good algorithm, smaller base)
          - Kitsu: 0.3 (alternative perspective)

        Returns:
            Weighted average rating (0-10 scale)
        """
        ratings = []
        weights = []

        if self.rating_mal is not None:
            ratings.append(self.rating_mal)
            weights.append(0.4)

        if self.rating_anilist is not None:
            # Convert AniList 0-100 to 0-10
            ratings.append(self.rating_anilist / 10.0)
            weights.append(0.3)

        if self.rating_kitsu is not None:
            # Convert Kitsu 0-100 to 0-10
            ratings.append(self.rating_kitsu / 10.0)
            weights.append(0.3)

        if not ratings:
            return 0.0

        # Normalize weights to sum to 1.0
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]

        # Weighted average
        weighted_sum = sum(r * w for r, w in zip(ratings, normalized_weights))
        return round(weighted_sum, 2)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'negus_id': self.negus_id,
            'mappings': self.mappings,
            'titles': self.titles,
            'alt_titles': self.alt_titles,
            'synopsis': self.synopsis,
            'status': self.status.value if self.status else None,
            'manga_type': self.manga_type.value if self.manga_type else None,
            'genres': self.genres,
            'tags': self.tags,
            'themes': self.themes,
            'demographics': self.demographics,
            'author': self.author,
            'artist': self.artist,
            'rating': self.rating,
            'rating_anilist': self.rating_anilist,
            'rating_mal': self.rating_mal,
            'rating_kitsu': self.rating_kitsu,
            'popularity': self.popularity,
            'rank': self.rank,
            'volumes': self.volumes,
            'chapters': self.chapters,
            'cover_image': self.cover_image,
            'banner_image': self.banner_image,
            'year': self.year,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'links': [{'site': l.site, 'url': l.url} for l in self.links],
            'is_adult': self.is_adult,
            'is_licensed': self.is_licensed,
            'last_updated': self.last_updated,
            'primary_source': self.primary_source
        }


@dataclass
class IDMapping:
    """
    ID mapping between different metadata providers.

    Used by the fuzzy matcher to store confirmed mappings
    with confidence scores.
    """
    source_title: str  # Original title used for matching

    # External IDs
    anilist_id: Optional[str] = None
    mal_id: Optional[str] = None
    kitsu_id: Optional[str] = None
    shikimori_id: Optional[str] = None
    mangaupdates_id: Optional[str] = None

    # Matching metadata
    confidence: float = 0.0  # 0-100
    matched_title: str = ""  # Title that was matched on provider

    # Timestamp
    created_at: float = 0.0  # Unix timestamp
