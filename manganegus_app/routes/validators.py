"""Lightweight request validation helpers."""

import re
from typing import Any, Dict, List, Tuple, Optional, Set


Rule = Tuple[str, type, Optional[int]]

# Allowed source IDs - populated at runtime from SourceManager
_allowed_source_ids: Set[str] = set()

# Safe characters for source IDs (alphanumeric, dash, underscore)
SOURCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# Pagination limits
MAX_PAGE = 1000
MAX_LIMIT = 500


def set_allowed_sources(source_ids: List[str]) -> None:
    """Set the list of valid source IDs (called during app init)."""
    global _allowed_source_ids
    _allowed_source_ids = set(source_ids)


def validate_fields(payload: Dict[str, Any], rules: List[Rule]) -> Optional[str]:
    """
    Validate required fields with optional max length.

    Args:
        payload: Incoming JSON dict.
        rules: List of (field, type, max_length or None).

    Returns:
        None if valid, or error message string.
    """
    for field, expected_type, max_len in rules:
        if field not in payload:
            return f"Missing required field: {field}"
        value = payload.get(field)
        if not isinstance(value, expected_type):
            return f"Field '{field}' must be {expected_type.__name__}"
        if max_len is not None and len(str(value)) > max_len:
            return f"Field '{field}' exceeds max length {max_len}"
    return None


def validate_source_id(source_id: Optional[str]) -> Optional[str]:
    """
    Validate a source ID against known sources and safe character pattern.

    Returns:
        None if valid, or error message string.
    """
    if not source_id:
        return "Missing source ID"

    # Check character pattern (prevent injection)
    if not SOURCE_ID_PATTERN.match(source_id):
        return "Invalid source ID format"

    # Check against known sources (if populated)
    if _allowed_source_ids and source_id not in _allowed_source_ids:
        # Allow 'jikan' pseudo-source even if not in list
        if source_id != 'jikan':
            return f"Unknown source: {source_id}"

    return None


def validate_pagination(page: Any, limit: Any = None) -> Tuple[int, int, Optional[str]]:
    """
    Validate and sanitize pagination parameters.

    Args:
        page: Page number (1-indexed)
        limit: Items per page (optional)

    Returns:
        Tuple of (sanitized_page, sanitized_limit, error_or_none)
    """
    # Validate page
    try:
        page_int = int(page) if page is not None else 1
    except (ValueError, TypeError):
        return 1, 20, "Invalid page number"

    if page_int < 1:
        page_int = 1
    elif page_int > MAX_PAGE:
        return 1, 20, f"Page number exceeds maximum ({MAX_PAGE})"

    # Validate limit
    try:
        limit_int = int(limit) if limit is not None else 20
    except (ValueError, TypeError):
        limit_int = 20

    if limit_int < 1:
        limit_int = 20
    elif limit_int > MAX_LIMIT:
        limit_int = MAX_LIMIT  # Cap at max instead of error

    return page_int, limit_int, None


def sanitize_string(value: str, max_length: int = 500, allow_newlines: bool = False) -> str:
    """
    Sanitize a string by removing control characters and limiting length.

    Args:
        value: String to sanitize
        max_length: Maximum allowed length
        allow_newlines: Whether to allow newlines

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        return ""

    # Remove control characters (except newlines if allowed)
    if allow_newlines:
        result = ''.join(c for c in value if c >= ' ' or c in '\n\r\t')
    else:
        result = ''.join(c for c in value if c >= ' ')

    # Limit length
    return result[:max_length]
