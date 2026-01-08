"""Lightweight request validation helpers."""

from typing import Any, Dict, List, Tuple, Optional


Rule = Tuple[str, type, Optional[int]]


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
