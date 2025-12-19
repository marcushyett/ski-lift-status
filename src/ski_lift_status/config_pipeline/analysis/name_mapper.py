"""Name mapper for mapping online data names to OpenSkiMap IDs.

This module maps lift/run names from online status pages to the
reference data in lifts.csv and runs.csv, handling fuzzy matching
and deduplication by locality.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process


@dataclass
class NameMapping:
    """A mapping from online name to OpenSkiMap ID."""

    online_name: str  # Name from the website/API
    openskimap_id: str  # OpenSkiMap ID
    openskimap_name: str  # Name in OpenSkiMap data
    match_type: str  # "exact", "case_insensitive", "fuzzy"
    confidence: float  # 0.0 to 1.0
    locality: str | None = None
    entity_type: str = "lift"  # "lift" or "run"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "online_name": self.online_name,
            "openskimap_id": self.openskimap_id,
            "openskimap_name": self.openskimap_name,
            "match_type": self.match_type,
            "confidence": self.confidence,
            "locality": self.locality,
            "entity_type": self.entity_type,
        }


@dataclass
class MappingResult:
    """Result of name mapping operation."""

    entity_type: str  # "lift" or "run"
    total_online_names: int
    total_reference_entities: int
    mapped_count: int
    unmapped_online: list[str] = field(default_factory=list)
    unmapped_reference: list[str] = field(default_factory=list)
    mappings: list[NameMapping] = field(default_factory=list)
    coverage_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type,
            "total_online_names": self.total_online_names,
            "total_reference_entities": self.total_reference_entities,
            "mapped_count": self.mapped_count,
            "unmapped_online": self.unmapped_online[:20],
            "unmapped_reference": self.unmapped_reference[:20],
            "mappings": [m.to_dict() for m in self.mappings],
            "coverage_percent": self.coverage_percent,
        }


def _normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    s = name.strip().lower()
    # Remove common prefixes/suffixes
    s = re.sub(r'^(le|la|les|l\'|the|der|die|das)\s+', '', s)
    # Normalize separators
    s = re.sub(r'[-_\s]+', ' ', s)
    # Remove accents (simplified)
    s = s.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
    s = s.replace('à', 'a').replace('â', 'a')
    s = s.replace('ü', 'u').replace('ö', 'o').replace('ä', 'a')
    return s.strip()


def deduplicate_by_locality(
    entities: list[dict],
    name_field: str = "name",
    locality_field: str = "localities",
    type_field: str | None = None,
) -> list[dict]:
    """Deduplicate entities by name and locality.

    Ski areas often have multiple lifts/runs with the same name in different
    localities. This groups them and keeps a representative entry.

    Args:
        entities: List of entity dictionaries.
        name_field: Field containing the name.
        locality_field: Field containing locality info.
        type_field: Optional field containing type (e.g., lift_type).

    Returns:
        Deduplicated list with representative entities.
    """
    # Group by normalized name
    groups: dict[str, list[dict]] = {}

    for entity in entities:
        name = entity.get(name_field, "").strip()
        if not name:
            continue

        norm_name = _normalize_name(name)
        key = norm_name

        # Include type in key if available
        if type_field and entity.get(type_field):
            key = f"{norm_name}:{entity[type_field]}"

        if key not in groups:
            groups[key] = []
        groups[key].append(entity)

    # Select representative from each group
    result: list[dict] = []

    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
        else:
            # Prefer entries with locality info
            with_locality = [e for e in group if e.get(locality_field)]
            if with_locality:
                result.append(with_locality[0])
            else:
                result.append(group[0])

            # Mark as having duplicates
            result[-1]["_duplicate_count"] = len(group)

    return result


def map_names_to_openskimap(
    online_names: list[str],
    reference_entities: list[dict],
    entity_type: str = "lift",
    name_field: str = "name",
    id_field: str = "id",
    locality_field: str = "localities",
    fuzzy_threshold: int = 80,
) -> MappingResult:
    """Map online names to OpenSkiMap reference data.

    Args:
        online_names: List of names from the online source.
        reference_entities: List of reference entity dictionaries.
        entity_type: "lift" or "run".
        name_field: Field containing the name in reference data.
        id_field: Field containing the ID in reference data.
        locality_field: Field containing locality info.
        fuzzy_threshold: Minimum fuzzy match score (0-100).

    Returns:
        MappingResult with all mappings and statistics.
    """
    result = MappingResult(
        entity_type=entity_type,
        total_online_names=len(online_names),
        total_reference_entities=len(reference_entities),
    )

    # Build lookup structures
    exact_lookup: dict[str, dict] = {}
    lower_lookup: dict[str, dict] = {}
    norm_lookup: dict[str, dict] = {}

    for entity in reference_entities:
        name = entity.get(name_field, "").strip()
        if not name:
            continue

        exact_lookup[name] = entity
        lower_lookup[name.lower()] = entity
        norm_lookup[_normalize_name(name)] = entity

    # Reference names for fuzzy matching
    reference_names = [e.get(name_field, "") for e in reference_entities if e.get(name_field)]

    # Track what's been mapped
    mapped_online = set()
    mapped_reference_ids = set()
    mappings: list[NameMapping] = []

    for online_name in online_names:
        online_name = online_name.strip()
        if not online_name:
            continue

        # Try exact match
        if online_name in exact_lookup:
            entity = exact_lookup[online_name]
            mappings.append(NameMapping(
                online_name=online_name,
                openskimap_id=entity.get(id_field, ""),
                openskimap_name=entity.get(name_field, ""),
                match_type="exact",
                confidence=1.0,
                locality=entity.get(locality_field),
                entity_type=entity_type,
            ))
            mapped_online.add(online_name)
            mapped_reference_ids.add(entity.get(id_field, ""))
            continue

        # Try case-insensitive match
        online_lower = online_name.lower()
        if online_lower in lower_lookup:
            entity = lower_lookup[online_lower]
            mappings.append(NameMapping(
                online_name=online_name,
                openskimap_id=entity.get(id_field, ""),
                openskimap_name=entity.get(name_field, ""),
                match_type="case_insensitive",
                confidence=0.95,
                locality=entity.get(locality_field),
                entity_type=entity_type,
            ))
            mapped_online.add(online_name)
            mapped_reference_ids.add(entity.get(id_field, ""))
            continue

        # Try normalized match
        online_norm = _normalize_name(online_name)
        if online_norm in norm_lookup:
            entity = norm_lookup[online_norm]
            mappings.append(NameMapping(
                online_name=online_name,
                openskimap_id=entity.get(id_field, ""),
                openskimap_name=entity.get(name_field, ""),
                match_type="normalized",
                confidence=0.9,
                locality=entity.get(locality_field),
                entity_type=entity_type,
            ))
            mapped_online.add(online_name)
            mapped_reference_ids.add(entity.get(id_field, ""))
            continue

        # Try fuzzy match
        if len(online_name) >= 3:  # Only fuzzy match longer names
            best = process.extractOne(
                online_name,
                reference_names,
                scorer=fuzz.ratio,
            )
            if best and best[1] >= fuzzy_threshold:
                matched_name = best[0]
                entity = exact_lookup.get(matched_name) or lower_lookup.get(matched_name.lower())
                if entity:
                    mappings.append(NameMapping(
                        online_name=online_name,
                        openskimap_id=entity.get(id_field, ""),
                        openskimap_name=entity.get(name_field, ""),
                        match_type="fuzzy",
                        confidence=best[1] / 100.0,
                        locality=entity.get(locality_field),
                        entity_type=entity_type,
                    ))
                    mapped_online.add(online_name)
                    mapped_reference_ids.add(entity.get(id_field, ""))
                    continue

    # Calculate statistics
    result.mappings = mappings
    result.mapped_count = len(mappings)
    result.unmapped_online = [n for n in online_names if n not in mapped_online]
    result.unmapped_reference = [
        e.get(name_field, "")
        for e in reference_entities
        if e.get(id_field, "") not in mapped_reference_ids
    ]

    if result.total_reference_entities > 0:
        result.coverage_percent = (len(mapped_reference_ids) / result.total_reference_entities) * 100

    return result


def load_reference_data(
    resort_id: str,
    lifts_csv_path: str | Path,
    runs_csv_path: str | Path,
) -> tuple[list[dict], list[dict]]:
    """Load reference data for a resort from CSV files.

    Args:
        resort_id: OpenSkiMap resort ID.
        lifts_csv_path: Path to lifts.csv.
        runs_csv_path: Path to runs.csv.

    Returns:
        Tuple of (lifts, runs) lists.
    """
    lifts = []
    runs = []

    # Load lifts
    with open(lifts_csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if resort_id in row.get("ski_area_ids", ""):
                lifts.append({
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "lift_type": row.get("lift_type", ""),
                    "status": row.get("status", ""),
                    "localities": row.get("localities", ""),
                })

    # Load runs
    with open(runs_csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if resort_id in row.get("ski_area_ids", ""):
                name = row.get("name", "").strip()
                if name:  # Skip unnamed runs
                    runs.append({
                        "id": row.get("id", ""),
                        "name": name,
                        "difficulty": row.get("difficulty", ""),
                        "run_type": row.get("run_type", ""),
                        "status": row.get("status", ""),
                        "localities": row.get("localities", ""),
                    })

    return lifts, runs
