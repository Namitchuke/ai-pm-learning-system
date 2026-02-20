"""
app/utils/validators.py — JSON schema validation and safe JSON parsing
TDD v2.0 §Utilities (validators.py)
PRD v2.0 §NFR-05 Data Integrity
FRD v2.0 §FS-11.1 Schema Versioning
"""
from __future__ import annotations

import json
from typing import Any, Optional, Type, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# Current supported schema version
CURRENT_SCHEMA_VERSION = "2.0"


def safe_parse_json(text: str) -> Optional[dict[str, Any]]:
    """
    Safely parse JSON text. Returns None on failure (no exception raised).
    Logs the parse error for debugging.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.debug(f"JSON parse failed: {exc} | Text: {text[:200]!r}")
        return None


def validate_schema_version(data: dict[str, Any], filename: str) -> bool:
    """
    NFR-05 / FRD FS-11.1: Check schema_version field on read.
    Logs a warning if version mismatch (does not fail hard — migrate-in-place strategy).
    """
    version = data.get("schema_version")
    if version is None:
        logger.warning(f"{filename}: missing schema_version. May be a legacy file.")
        return True  # Allow — migration handled by caller
    if version != CURRENT_SCHEMA_VERSION:
        logger.warning(
            f"{filename}: schema_version {version!r} != {CURRENT_SCHEMA_VERSION!r}. "
            f"Will attempt compatible read."
        )
    return True


def parse_model_safe(
    model_class: Type[T],
    data: dict[str, Any],
    context: str = "",
) -> Optional[T]:
    """
    Parse and validate a dict into a Pydantic model. Returns None on validation failure.
    Logs the validation errors for debugging.
    """
    try:
        return model_class(**data)
    except ValidationError as exc:
        logger.error(
            f"Schema validation failed for {model_class.__name__} "
            f"(context: {context}): {exc}"
        )
        return None
    except Exception as exc:
        logger.error(f"Unexpected parse error for {model_class.__name__}: {exc}")
        return None


def ensure_list(value: Any, field_name: str = "") -> list:
    """Ensure a value is a list. If not, return empty list with a warning."""
    if isinstance(value, list):
        return value
    logger.warning(f"Expected list for {field_name!r}, got {type(value).__name__}. Using [].")
    return []


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a float value between min and max."""
    return max(min_val, min(max_val, value))


def extract_float_from_dict(
    d: dict[str, Any],
    key: str,
    default: float = 0.0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> float:
    """Safely extract a float from a dict, with optional clamping."""
    try:
        val = float(d.get(key, default))
        if min_val is not None and max_val is not None:
            val = clamp(val, min_val, max_val)
        return val
    except (TypeError, ValueError):
        return default


def parse_gemini_score_response(
    text: str,
    expected_fields: list[str],
) -> Optional[dict[str, Any]]:
    """
    Parse and validate a Gemini scoring response.
    FRD FS-02.3: Scoring response must include all expected fields.
    Returns None if any required field is missing or invalid.
    """
    data = safe_parse_json(text)
    if data is None:
        return None

    for field in expected_fields:
        if field not in data:
            logger.warning(f"Gemini response missing field: {field!r}")
            return None

    return data
