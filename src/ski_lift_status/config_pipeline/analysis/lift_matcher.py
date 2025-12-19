"""Lift name matching in captured network resources.

This module finds which resources contain lift names from the reference
data (lifts.csv) using case-insensitive matching and fuzzy matching.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process


@dataclass
class LiftMatch:
    """A single lift name match found in content."""

    lift_id: str
    lift_name: str
    matched_text: str
    match_type: str  # "exact", "case_insensitive", "fuzzy"
    confidence: float  # 0.0 to 1.0
    position: int  # Character position in content
    context: str  # Surrounding text


@dataclass
class LiftMatchResult:
    """Result of searching a resource for lift names."""

    resource_url: str
    matches: list[LiftMatch] = field(default_factory=list)
    unique_lifts_found: int = 0
    total_lifts_expected: int = 0
    coverage_percent: float = 0.0
    match_density: float = 0.0  # Matches per 1000 chars

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_url": self.resource_url,
            "matches": [
                {
                    "lift_id": m.lift_id,
                    "lift_name": m.lift_name,
                    "matched_text": m.matched_text,
                    "match_type": m.match_type,
                    "confidence": m.confidence,
                    "position": m.position,
                    "context": m.context,
                }
                for m in self.matches
            ],
            "unique_lifts_found": self.unique_lifts_found,
            "total_lifts_expected": self.total_lifts_expected,
            "coverage_percent": self.coverage_percent,
            "match_density": self.match_density,
        }


def load_lifts_for_resort(resort_id: str, lifts_csv_path: str | Path) -> list[dict]:
    """Load lift data for a specific resort from lifts.csv.

    Args:
        resort_id: The OpenSkiMap resort ID.
        lifts_csv_path: Path to lifts.csv file.

    Returns:
        List of lift dictionaries with id, name, lift_type, etc.
    """
    lifts = []
    lifts_csv_path = Path(lifts_csv_path)

    with open(lifts_csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Check if this lift belongs to the resort
            ski_area_ids = row.get("ski_area_ids", "")
            if resort_id in ski_area_ids:
                lifts.append({
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "lift_type": row.get("lift_type", ""),
                    "status": row.get("status", ""),
                    "localities": row.get("localities", ""),
                })

    return lifts


def _extract_context(content: str, position: int, context_size: int = 50) -> str:
    """Extract surrounding context from content."""
    start = max(0, position - context_size)
    end = min(len(content), position + context_size)
    context = content[start:end]
    # Clean up whitespace
    context = re.sub(r'\s+', ' ', context).strip()
    return context


def find_lift_names_in_content(
    content: str,
    lifts: list[dict],
    fuzzy_threshold: int = 85,
) -> list[LiftMatch]:
    """Find lift names in content using exact, case-insensitive, and fuzzy matching.

    Args:
        content: The text content to search.
        lifts: List of lift dictionaries with 'id' and 'name' keys.
        fuzzy_threshold: Minimum fuzzy match score (0-100).

    Returns:
        List of LiftMatch objects for all found matches.
    """
    matches: list[LiftMatch] = []
    content_lower = content.lower()

    for lift in lifts:
        lift_name = lift.get("name", "").strip()
        lift_id = lift.get("id", "")

        if not lift_name or len(lift_name) < 2:
            continue

        lift_name_lower = lift_name.lower()

        # 1. Exact match
        pos = content.find(lift_name)
        if pos >= 0:
            matches.append(LiftMatch(
                lift_id=lift_id,
                lift_name=lift_name,
                matched_text=lift_name,
                match_type="exact",
                confidence=1.0,
                position=pos,
                context=_extract_context(content, pos),
            ))
            continue

        # 2. Case-insensitive match
        pos = content_lower.find(lift_name_lower)
        if pos >= 0:
            matched_text = content[pos:pos + len(lift_name)]
            matches.append(LiftMatch(
                lift_id=lift_id,
                lift_name=lift_name,
                matched_text=matched_text,
                match_type="case_insensitive",
                confidence=0.95,
                position=pos,
                context=_extract_context(content, pos),
            ))
            continue

        # 3. Fuzzy match - search for similar strings
        # Extract potential name candidates from content (words of similar length)
        name_len = len(lift_name)
        min_len = max(3, name_len - 3)
        max_len = name_len + 3

        # Use regex to find word sequences of appropriate length
        pattern = r'\b[\w\s-]{' + str(min_len) + ',' + str(max_len) + r'}\b'
        candidates = re.findall(pattern, content, re.IGNORECASE)

        if candidates:
            # Find best fuzzy match
            best = process.extractOne(
                lift_name_lower,
                [c.lower() for c in candidates],
                scorer=fuzz.ratio,
            )
            if best and best[1] >= fuzzy_threshold:
                matched_text = best[0]
                # Find position of this match
                pos = content_lower.find(matched_text.lower())
                if pos >= 0:
                    matches.append(LiftMatch(
                        lift_id=lift_id,
                        lift_name=lift_name,
                        matched_text=matched_text,
                        match_type="fuzzy",
                        confidence=best[1] / 100.0,
                        position=pos,
                        context=_extract_context(content, pos),
                    ))

    return matches


def analyze_resources_for_lifts(
    resources: list[dict],  # List of CapturedResource.to_dict()
    lifts: list[dict],
    fuzzy_threshold: int = 85,
) -> list[LiftMatchResult]:
    """Analyze multiple resources for lift name matches.

    Args:
        resources: List of captured resource dictionaries.
        lifts: List of lift dictionaries from lifts.csv.
        fuzzy_threshold: Minimum fuzzy match score.

    Returns:
        List of LiftMatchResult, sorted by coverage (highest first).
    """
    results: list[LiftMatchResult] = []
    total_lifts = len(lifts)

    for resource in resources:
        body = resource.get("body", "")
        url = resource.get("url", "")

        if not body:
            continue

        matches = find_lift_names_in_content(body, lifts, fuzzy_threshold)

        # Count unique lifts found
        unique_lift_ids = set(m.lift_id for m in matches)
        unique_count = len(unique_lift_ids)

        # Calculate coverage
        coverage = (unique_count / total_lifts * 100) if total_lifts > 0 else 0

        # Calculate match density
        density = (len(matches) / len(body) * 1000) if body else 0

        results.append(LiftMatchResult(
            resource_url=url,
            matches=matches,
            unique_lifts_found=unique_count,
            total_lifts_expected=total_lifts,
            coverage_percent=coverage,
            match_density=density,
        ))

    # Sort by coverage (highest first)
    results.sort(key=lambda r: r.coverage_percent, reverse=True)

    return results
