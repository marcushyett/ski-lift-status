"""Foreign key detector between data sources.

This module identifies which fields can be used to link static and
dynamic data sources together (e.g., matching IDs or names between
a lift list API and a status API).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from collections import Counter


@dataclass
class ForeignKeyCandidate:
    """A candidate foreign key relationship."""

    source_field: str  # Field in source data
    target_field: str  # Field in target data
    match_count: int  # Number of matches found
    source_cardinality: int  # Unique values in source
    target_cardinality: int  # Unique values in target
    coverage_percent: float  # Percentage of source matched in target
    match_type: str  # "exact", "case_insensitive", "fuzzy"
    sample_matches: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_field": self.source_field,
            "target_field": self.target_field,
            "match_count": self.match_count,
            "source_cardinality": self.source_cardinality,
            "target_cardinality": self.target_cardinality,
            "coverage_percent": self.coverage_percent,
            "match_type": self.match_type,
            "sample_matches": self.sample_matches[:5],
        }


@dataclass
class ForeignKeyResult:
    """Result of foreign key detection."""

    source_url: str
    target_url: str
    candidates: list[ForeignKeyCandidate] = field(default_factory=list)
    best_candidate: ForeignKeyCandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_url": self.source_url,
            "target_url": self.target_url,
            "candidates": [c.to_dict() for c in self.candidates],
            "best_candidate": self.best_candidate.to_dict() if self.best_candidate else None,
        }


def _extract_field_values(data: Any, max_depth: int = 5) -> dict[str, list[Any]]:
    """Extract all field values from JSON data.

    Returns dict mapping field path to list of values found.
    """
    result: dict[str, list[Any]] = {}

    def traverse(obj: Any, path: str, depth: int) -> None:
        if depth > max_depth:
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                child_path = f"{path}.{key}" if path else key

                # Store primitive values
                if isinstance(value, (str, int, float)):
                    if child_path not in result:
                        result[child_path] = []
                    result[child_path].append(value)

                # Recurse
                traverse(value, child_path, depth + 1)

        elif isinstance(obj, list):
            for i, item in enumerate(obj[:100]):  # Limit array items
                traverse(item, path, depth + 1)

    traverse(data, "", 0)
    return result


def _normalize_value(value: Any) -> str:
    """Normalize a value for comparison."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    # Remove common separators
    s = re.sub(r'[-_\s]+', ' ', s)
    return s


def _compute_matches(
    source_values: list[Any],
    target_values: list[Any],
    match_type: str = "exact",
) -> tuple[int, list[tuple[str, str]]]:
    """Compute matches between source and target values.

    Returns (match_count, sample_matches).
    """
    matches: list[tuple[str, str]] = []

    if match_type == "exact":
        target_set = set(str(v) for v in target_values)
        for sv in source_values:
            s = str(sv)
            if s in target_set:
                matches.append((s, s))

    elif match_type == "case_insensitive":
        target_lower = {str(v).lower(): str(v) for v in target_values}
        for sv in source_values:
            s_lower = str(sv).lower()
            if s_lower in target_lower:
                matches.append((str(sv), target_lower[s_lower]))

    elif match_type == "normalized":
        target_norm = {_normalize_value(v): str(v) for v in target_values}
        for sv in source_values:
            s_norm = _normalize_value(sv)
            if s_norm in target_norm:
                matches.append((str(sv), target_norm[s_norm]))

    return len(matches), matches


def detect_foreign_keys(
    source_content: str,
    target_content: str,
    source_url: str = "",
    target_url: str = "",
    min_coverage: float = 10.0,
) -> ForeignKeyResult:
    """Detect potential foreign key relationships between two JSON data sources.

    Args:
        source_content: JSON content of source (e.g., static lift data).
        target_content: JSON content of target (e.g., dynamic status data).
        source_url: URL of source for reference.
        target_url: URL of target for reference.
        min_coverage: Minimum coverage percentage to consider a candidate.

    Returns:
        ForeignKeyResult with candidates and best match.
    """
    result = ForeignKeyResult(source_url=source_url, target_url=target_url)

    try:
        source_data = json.loads(source_content)
        target_data = json.loads(target_content)
    except json.JSONDecodeError:
        return result

    # Extract field values
    source_fields = _extract_field_values(source_data)
    target_fields = _extract_field_values(target_data)

    candidates: list[ForeignKeyCandidate] = []

    # Compare all field combinations
    for source_field, source_values in source_fields.items():
        if not source_values:
            continue

        source_unique = set(str(v) for v in source_values)
        source_cardinality = len(source_unique)

        # Skip fields with too few or too many unique values
        if source_cardinality < 2 or source_cardinality > 1000:
            continue

        for target_field, target_values in target_fields.items():
            if not target_values:
                continue

            target_unique = set(str(v) for v in target_values)
            target_cardinality = len(target_unique)

            if target_cardinality < 2 or target_cardinality > 1000:
                continue

            # Try different match types
            for match_type in ["exact", "case_insensitive", "normalized"]:
                match_count, sample_matches = _compute_matches(
                    list(source_unique),
                    list(target_unique),
                    match_type,
                )

                if match_count == 0:
                    continue

                coverage = (match_count / source_cardinality) * 100

                if coverage >= min_coverage:
                    candidates.append(ForeignKeyCandidate(
                        source_field=source_field,
                        target_field=target_field,
                        match_count=match_count,
                        source_cardinality=source_cardinality,
                        target_cardinality=target_cardinality,
                        coverage_percent=coverage,
                        match_type=match_type,
                        sample_matches=sample_matches[:10],
                    ))

    # Sort by coverage and match count
    candidates.sort(
        key=lambda c: (c.coverage_percent, c.match_count),
        reverse=True,
    )

    result.candidates = candidates[:20]  # Top 20 candidates

    # Select best candidate
    if candidates:
        # Prefer exact matches with high coverage
        for c in candidates:
            if c.match_type == "exact" and c.coverage_percent >= 50:
                result.best_candidate = c
                break

        if not result.best_candidate:
            result.best_candidate = candidates[0]

    return result


def find_best_foreign_key(
    source_content: str,
    target_content: str,
    preferred_fields: list[str] | None = None,
) -> ForeignKeyCandidate | None:
    """Find the best foreign key relationship.

    Args:
        source_content: JSON content of source.
        target_content: JSON content of target.
        preferred_fields: List of preferred field names (e.g., ["id", "name"]).

    Returns:
        Best ForeignKeyCandidate or None.
    """
    result = detect_foreign_keys(source_content, target_content)

    if not result.candidates:
        return None

    # If preferred fields specified, prioritize those
    if preferred_fields:
        for pf in preferred_fields:
            for c in result.candidates:
                if pf.lower() in c.source_field.lower() or pf.lower() in c.target_field.lower():
                    if c.coverage_percent >= 20:  # Reasonable coverage
                        return c

    return result.best_candidate
