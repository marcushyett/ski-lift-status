"""Cross-source mapper for establishing foreign key relationships."""

import re
from difflib import SequenceMatcher
from typing import Any

from ..models import Lift, Run
from .models import (
    DataCategory,
    SchemaOverview,
    SourceMapping,
)


def _normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching."""
    if not text:
        return ""
    # Lowercase, remove special chars, collapse whitespace
    normalized = text.lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _fuzzy_similarity(s1: str, s2: str) -> float:
    """Calculate fuzzy similarity between two strings."""
    if not s1 or not s2:
        return 0.0

    n1 = _normalize_for_matching(s1)
    n2 = _normalize_for_matching(s2)

    if n1 == n2:
        return 1.0

    # Use SequenceMatcher for similarity
    return SequenceMatcher(None, n1, n2).ratio()


def _contains_similarity(s1: str, s2: str) -> float:
    """Check if one string contains the other (normalized)."""
    if not s1 or not s2:
        return 0.0

    n1 = _normalize_for_matching(s1)
    n2 = _normalize_for_matching(s2)

    if n1 in n2 or n2 in n1:
        return 0.9

    # Check if all words of shorter string are in longer
    shorter, longer = (n1, n2) if len(n1) < len(n2) else (n2, n1)
    shorter_words = set(shorter.split())
    longer_words = set(longer.split())

    if shorter_words and shorter_words.issubset(longer_words):
        return 0.8

    return 0.0


def _extract_field_values(
    objects: list[dict[str, Any]],
    field_name: str,
) -> list[str]:
    """Extract all values for a field from a list of objects."""
    values = []
    for obj in objects:
        if field_name in obj and obj[field_name]:
            values.append(str(obj[field_name]))
    return values


def _find_matching_field(
    source_schema: SchemaOverview,
    target_schema: SchemaOverview,
    min_match_ratio: float = 0.5,
) -> tuple[str, str, str, float] | None:
    """Find the best matching field between two schemas.

    Returns:
        Tuple of (source_field, target_field, match_type, confidence) or None.
    """
    # Get potential join key fields from source
    source_key_fields = [
        f for f in source_schema.fields
        if f.is_identifier or f.is_name_field
    ]

    # Get potential join key fields from target
    target_key_fields = [
        f for f in target_schema.fields
        if f.is_identifier or f.is_name_field
    ]

    if not source_key_fields or not target_key_fields:
        return None

    best_match = None
    best_score = 0.0

    for source_field in source_key_fields:
        source_values = source_field.sample_values

        for target_field in target_key_fields:
            target_values = target_field.sample_values

            if not source_values or not target_values:
                continue

            # Calculate match score between sample values
            matches = 0.0
            total = 0

            for sv in source_values[:10]:
                sv_str = str(sv)
                for tv in target_values[:10]:
                    tv_str = str(tv)
                    total += 1

                    # Check exact match
                    if _normalize_for_matching(sv_str) == _normalize_for_matching(tv_str):
                        matches += 1
                        continue

                    # Check fuzzy match
                    sim = _fuzzy_similarity(sv_str, tv_str)
                    if sim >= 0.8:
                        matches += 0.8
                        continue

                    # Check contains match
                    contains = _contains_similarity(sv_str, tv_str)
                    if contains > 0:
                        matches += contains

            if total > 0:
                match_ratio = matches / total
                if match_ratio > best_score and match_ratio >= min_match_ratio:
                    best_score = match_ratio

                    # Determine match type
                    if match_ratio >= 0.9:
                        match_type = "exact"
                    elif match_ratio >= 0.7:
                        match_type = "fuzzy"
                    else:
                        match_type = "contains"

                    best_match = (
                        source_field.name,
                        target_field.name,
                        match_type,
                        match_ratio,
                    )

    return best_match


class SourceMapper:
    """Maps relationships between static and dynamic data sources."""

    def __init__(
        self,
        reference_lifts: list[Lift] | None = None,
        reference_runs: list[Run] | None = None,
    ):
        """Initialize the mapper.

        Args:
            reference_lifts: OpenSkiMap lift data for validation.
            reference_runs: OpenSkiMap run data for validation.
        """
        self.reference_lifts = reference_lifts or []
        self.reference_runs = reference_runs or []

        # Extract reference names for validation
        self.lift_names = [lift.name for lift in self.reference_lifts if lift.name]
        self.run_names = [run.name for run in self.reference_runs if run.name]

    def find_mapping(
        self,
        static_schema: SchemaOverview,
        dynamic_schema: SchemaOverview,
    ) -> SourceMapping | None:
        """Find mapping between static and dynamic schemas.

        Args:
            static_schema: Schema for static metadata source.
            dynamic_schema: Schema for dynamic status source.

        Returns:
            SourceMapping if a valid mapping is found, None otherwise.
        """
        match = _find_matching_field(static_schema, dynamic_schema)

        if not match:
            return None

        source_field, target_field, match_type, confidence = match

        return SourceMapping(
            static_resource_url=static_schema.resource_url,
            dynamic_resource_url=dynamic_schema.resource_url,
            join_key_static=source_field,
            join_key_dynamic=target_field,
            match_type=match_type,
            confidence_score=confidence,
        )

    def find_all_mappings(
        self,
        schemas: dict[str, list[SchemaOverview]],
    ) -> list[SourceMapping]:
        """Find all valid mappings between schemas.

        Args:
            schemas: Dict of resource URLs to schema overviews.

        Returns:
            List of SourceMapping objects.
        """
        mappings = []

        # Separate schemas by category
        static_schemas = []
        dynamic_schemas = []

        for url, overviews in schemas.items():
            for overview in overviews:
                if overview.category == DataCategory.STATIC_METADATA:
                    static_schemas.append(overview)
                elif overview.category == DataCategory.DYNAMIC_STATUS:
                    dynamic_schemas.append(overview)
                elif overview.category == DataCategory.MIXED:
                    # Mixed can serve as both
                    static_schemas.append(overview)
                    dynamic_schemas.append(overview)

        # Find mappings between static and dynamic sources
        for static in static_schemas:
            for dynamic in dynamic_schemas:
                if static.resource_url == dynamic.resource_url:
                    continue  # Skip same resource

                mapping = self.find_mapping(static, dynamic)
                if mapping:
                    mappings.append(mapping)

        # Sort by confidence
        mappings.sort(key=lambda m: m.confidence_score, reverse=True)

        return mappings

    def validate_mapping_against_reference(
        self,
        mapping: SourceMapping,
        static_schema: SchemaOverview,
    ) -> tuple[float, float]:
        """Validate a mapping against OpenSkiMap reference data.

        Args:
            mapping: The source mapping to validate.
            static_schema: The static schema for extracting values.

        Returns:
            Tuple of (lift_coverage, run_coverage).
        """
        # Get values from the join key field
        join_field = next(
            (f for f in static_schema.fields if f.name == mapping.join_key_static),
            None,
        )

        if not join_field or not join_field.sample_values:
            return 0.0, 0.0

        sample_values = [str(v) for v in join_field.sample_values]

        # Check against lift names
        lift_matches = 0
        for name in self.lift_names:
            for value in sample_values:
                if _fuzzy_similarity(name, value) >= 0.7:
                    lift_matches += 1
                    break

        lift_coverage = lift_matches / len(self.lift_names) if self.lift_names else 0.0

        # Check against run names
        run_matches = 0
        for name in self.run_names:
            for value in sample_values:
                if _fuzzy_similarity(name, value) >= 0.7:
                    run_matches += 1
                    break

        run_coverage = run_matches / len(self.run_names) if self.run_names else 0.0

        return lift_coverage, run_coverage


def find_source_mappings(
    schemas: dict[str, list[SchemaOverview]],
    reference_lifts: list[Lift] | None = None,
    reference_runs: list[Run] | None = None,
) -> list[SourceMapping]:
    """Convenience function to find all source mappings.

    Args:
        schemas: Dict of resource URLs to schema overviews.
        reference_lifts: Optional reference lifts for validation.
        reference_runs: Optional reference runs for validation.

    Returns:
        List of SourceMapping objects.
    """
    mapper = SourceMapper(reference_lifts, reference_runs)
    return mapper.find_all_mappings(schemas)
