"""Run/piste name matching in captured network resources.

This module finds which resources contain run names from the reference
data (runs.csv) using case-insensitive matching and fuzzy matching.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process


@dataclass
class RunMatch:
    """A single run name match found in content."""

    run_id: str
    run_name: str
    matched_text: str
    match_type: str  # "exact", "case_insensitive", "fuzzy"
    confidence: float  # 0.0 to 1.0
    position: int  # Character position in content
    context: str  # Surrounding text
    difficulty: str | None = None


@dataclass
class RunMatchResult:
    """Result of searching a resource for run names."""

    resource_url: str
    matches: list[RunMatch] = field(default_factory=list)
    unique_runs_found: int = 0
    total_runs_expected: int = 0
    coverage_percent: float = 0.0
    match_density: float = 0.0  # Matches per 1000 chars

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_url": self.resource_url,
            "matches": [
                {
                    "run_id": m.run_id,
                    "run_name": m.run_name,
                    "matched_text": m.matched_text,
                    "match_type": m.match_type,
                    "confidence": m.confidence,
                    "position": m.position,
                    "context": m.context,
                    "difficulty": m.difficulty,
                }
                for m in self.matches
            ],
            "unique_runs_found": self.unique_runs_found,
            "total_runs_expected": self.total_runs_expected,
            "coverage_percent": self.coverage_percent,
            "match_density": self.match_density,
        }


def load_runs_for_resort(resort_id: str, runs_csv_path: str | Path) -> list[dict]:
    """Load run data for a specific resort from runs.csv.

    Args:
        resort_id: The OpenSkiMap resort ID.
        runs_csv_path: Path to runs.csv file.

    Returns:
        List of run dictionaries with id, name, difficulty, etc.
    """
    runs = []
    runs_csv_path = Path(runs_csv_path)

    with open(runs_csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Check if this run belongs to the resort
            ski_area_ids = row.get("ski_area_ids", "")
            if resort_id in ski_area_ids:
                name = row.get("name", "").strip()
                # Skip unnamed runs (many exist in the data)
                if name:
                    runs.append({
                        "id": row.get("id", ""),
                        "name": name,
                        "difficulty": row.get("difficulty", ""),
                        "run_type": row.get("run_type", ""),
                        "status": row.get("status", ""),
                        "localities": row.get("localities", ""),
                    })

    return runs


def _extract_context(content: str, position: int, context_size: int = 50) -> str:
    """Extract surrounding context from content."""
    start = max(0, position - context_size)
    end = min(len(content), position + context_size)
    context = content[start:end]
    # Clean up whitespace
    context = re.sub(r'\s+', ' ', context).strip()
    return context


def find_run_names_in_content(
    content: str,
    runs: list[dict],
    fuzzy_threshold: int = 85,
) -> list[RunMatch]:
    """Find run names in content using exact, case-insensitive, and fuzzy matching.

    Args:
        content: The text content to search.
        runs: List of run dictionaries with 'id', 'name', and 'difficulty' keys.
        fuzzy_threshold: Minimum fuzzy match score (0-100).

    Returns:
        List of RunMatch objects for all found matches.
    """
    matches: list[RunMatch] = []
    content_lower = content.lower()

    for run in runs:
        run_name = run.get("name", "").strip()
        run_id = run.get("id", "")
        difficulty = run.get("difficulty", "")

        if not run_name or len(run_name) < 2:
            continue

        run_name_lower = run_name.lower()

        # 1. Exact match
        pos = content.find(run_name)
        if pos >= 0:
            matches.append(RunMatch(
                run_id=run_id,
                run_name=run_name,
                matched_text=run_name,
                match_type="exact",
                confidence=1.0,
                position=pos,
                context=_extract_context(content, pos),
                difficulty=difficulty,
            ))
            continue

        # 2. Case-insensitive match
        pos = content_lower.find(run_name_lower)
        if pos >= 0:
            matched_text = content[pos:pos + len(run_name)]
            matches.append(RunMatch(
                run_id=run_id,
                run_name=run_name,
                matched_text=matched_text,
                match_type="case_insensitive",
                confidence=0.95,
                position=pos,
                context=_extract_context(content, pos),
                difficulty=difficulty,
            ))
            continue

        # 3. Fuzzy match - search for similar strings
        # Only do fuzzy matching for longer names (to avoid false positives)
        if len(run_name) < 4:
            continue

        name_len = len(run_name)
        min_len = max(3, name_len - 3)
        max_len = name_len + 3

        # Use regex to find word sequences of appropriate length
        pattern = r'\b[\w\s-]{' + str(min_len) + ',' + str(max_len) + r'}\b'
        candidates = re.findall(pattern, content, re.IGNORECASE)

        if candidates:
            # Find best fuzzy match
            best = process.extractOne(
                run_name_lower,
                [c.lower() for c in candidates],
                scorer=fuzz.ratio,
            )
            if best and best[1] >= fuzzy_threshold:
                matched_text = best[0]
                # Find position of this match
                pos = content_lower.find(matched_text.lower())
                if pos >= 0:
                    matches.append(RunMatch(
                        run_id=run_id,
                        run_name=run_name,
                        matched_text=matched_text,
                        match_type="fuzzy",
                        confidence=best[1] / 100.0,
                        position=pos,
                        context=_extract_context(content, pos),
                        difficulty=difficulty,
                    ))

    return matches


def analyze_resources_for_runs(
    resources: list[dict],  # List of CapturedResource.to_dict()
    runs: list[dict],
    fuzzy_threshold: int = 85,
) -> list[RunMatchResult]:
    """Analyze multiple resources for run name matches.

    Args:
        resources: List of captured resource dictionaries.
        runs: List of run dictionaries from runs.csv.
        fuzzy_threshold: Minimum fuzzy match score.

    Returns:
        List of RunMatchResult, sorted by coverage (highest first).
    """
    results: list[RunMatchResult] = []
    total_runs = len(runs)

    for resource in resources:
        body = resource.get("body", "")
        url = resource.get("url", "")

        if not body:
            continue

        matches = find_run_names_in_content(body, runs, fuzzy_threshold)

        # Count unique runs found
        unique_run_ids = set(m.run_id for m in matches)
        unique_count = len(unique_run_ids)

        # Calculate coverage
        coverage = (unique_count / total_runs * 100) if total_runs > 0 else 0

        # Calculate match density
        density = (len(matches) / len(body) * 1000) if body else 0

        results.append(RunMatchResult(
            resource_url=url,
            matches=matches,
            unique_runs_found=unique_count,
            total_runs_expected=total_runs,
            coverage_percent=coverage,
            match_density=density,
        ))

    # Sort by coverage (highest first)
    results.sort(key=lambda r: r.coverage_percent, reverse=True)

    return results
