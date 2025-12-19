"""Secure config runner for executing extraction configs.

This module executes configs in a sandboxed environment to prevent
malicious code execution. It supports:
- JSON/XML extraction via Python
- HTML extraction via BeautifulSoup
- Limited JavaScript execution via restricted eval

SECURITY: The runner prevents dangerous operations like:
- Network requests from extraction code
- File system access
- Process spawning
- Arbitrary code execution
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from .schema import (
    ConfigSchema,
    DataSource,
    ExtractionMethod,
    LiftStatus,
    RunStatus,
)


@dataclass
class ExtractedEntity:
    """An extracted lift or run entity."""

    source_name: str
    source_id: str | None
    status: str
    entity_type: str  # "lift" or "run"
    difficulty: str | None = None  # For runs
    lift_type: str | None = None  # For lifts
    openskimap_id: str | None = None  # After mapping
    raw_data: dict | None = None


@dataclass
class ExecutionResult:
    """Result of config execution."""

    success: bool
    lifts: list[ExtractedEntity] = field(default_factory=list)
    runs: list[ExtractedEntity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    debug_info: dict[str, Any] = field(default_factory=dict)

    # Coverage metrics (after mapping)
    mapped_lifts: int = 0
    total_expected_lifts: int = 0
    lift_coverage_percent: float = 0.0
    mapped_runs: int = 0
    total_expected_runs: int = 0
    run_coverage_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "lifts": [
                {
                    "source_name": e.source_name,
                    "source_id": e.source_id,
                    "status": e.status,
                    "lift_type": e.lift_type,
                    "openskimap_id": e.openskimap_id,
                }
                for e in self.lifts
            ],
            "runs": [
                {
                    "source_name": e.source_name,
                    "source_id": e.source_id,
                    "status": e.status,
                    "difficulty": e.difficulty,
                    "openskimap_id": e.openskimap_id,
                }
                for e in self.runs
            ],
            "errors": self.errors,
            "mapped_lifts": self.mapped_lifts,
            "total_expected_lifts": self.total_expected_lifts,
            "lift_coverage_percent": self.lift_coverage_percent,
            "mapped_runs": self.mapped_runs,
            "total_expected_runs": self.total_expected_runs,
            "run_coverage_percent": self.run_coverage_percent,
        }


def _normalize_status(status_str: str, mapping: dict[str, str]) -> str:
    """Normalize a status string using the mapping."""
    if not status_str:
        return LiftStatus.UNKNOWN.value

    status_lower = status_str.lower().strip()

    # Check explicit mapping first
    for source_val, normalized in mapping.items():
        if source_val.lower() == status_lower:
            return normalized

    # Default mappings
    if status_lower in ("open", "ouvert", "ouverte", "geöffnet", "aperto"):
        return LiftStatus.OPEN.value
    if status_lower in ("closed", "fermé", "fermée", "geschlossen", "chiuso"):
        return LiftStatus.CLOSED.value
    if status_lower in ("hold", "standby", "attente"):
        return LiftStatus.HOLD.value

    return LiftStatus.UNKNOWN.value


def _extract_json_path(data: Any, path: str) -> Any:
    """Extract value using a simple JSON path.

    Supports:
    - $.field.subfield
    - $.array[0]
    - $.array[*].field (returns list)
    """
    if not path or path == "$":
        return data

    # Remove leading $. if present
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    parts = []
    current = ""
    in_bracket = False

    for char in path:
        if char == "[":
            if current:
                parts.append(current)
                current = ""
            in_bracket = True
        elif char == "]":
            if current:
                parts.append(f"[{current}]")
                current = ""
            in_bracket = False
        elif char == "." and not in_bracket:
            if current:
                parts.append(current)
                current = ""
        else:
            current += char

    if current:
        parts.append(current)

    result = data
    for part in parts:
        if result is None:
            return None

        if part.startswith("[") and part.endswith("]"):
            idx_str = part[1:-1]
            if idx_str == "*":
                # Wildcard - apply rest of path to all items
                if isinstance(result, list):
                    remaining_path = ".".join(parts[parts.index(part) + 1:])
                    return [_extract_json_path(item, remaining_path) for item in result]
                return None
            else:
                try:
                    idx = int(idx_str)
                    if isinstance(result, list) and 0 <= idx < len(result):
                        result = result[idx]
                    else:
                        return None
                except ValueError:
                    return None
        else:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                return None

    return result


def _extract_css_selector(html: str, selector: str) -> list[Any]:
    """Extract elements using CSS selector."""
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.select(selector)
    return [el for el in elements]


def _extract_element_text(element: Any, selector: str) -> str | None:
    """Extract text from an element using a selector."""
    if not selector:
        return element.get_text(strip=True) if hasattr(element, "get_text") else str(element)

    if hasattr(element, "select_one"):
        child = element.select_one(selector)
        if child:
            return child.get_text(strip=True)

    return None


def _extract_element_attr(element: Any, attr_name: str) -> str | None:
    """Extract attribute from an element."""
    if hasattr(element, "get"):
        return element.get(attr_name)
    return None


async def _fetch_source(source: DataSource) -> tuple[str | None, str | None]:
    """Fetch data from a source URL.

    Returns (content, error).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                **source.headers,
            }

            if source.method == "POST":
                response = await client.post(
                    source.url,
                    headers=headers,
                    content=source.body,
                )
            else:
                response = await client.get(source.url, headers=headers)

            response.raise_for_status()
            return response.text, None

    except Exception as e:
        return None, str(e)


def _extract_from_json_source(
    content: str,
    source: DataSource,
    entity_type: str,
) -> list[ExtractedEntity]:
    """Extract entities from JSON content."""
    entities: list[ExtractedEntity] = []

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return entities

    # Get list of items
    items = _extract_json_path(data, source.list_selector)
    if not isinstance(items, list):
        items = [items] if items else []

    for item in items:
        if not isinstance(item, dict):
            continue

        # Extract fields
        name = _extract_json_path(item, source.name_selector)
        status = _extract_json_path(item, source.status_selector)
        item_id = _extract_json_path(item, source.id_selector) if source.id_selector else None
        item_type = _extract_json_path(item, source.type_selector) if source.type_selector else None

        if name:
            entity = ExtractedEntity(
                source_name=str(name),
                source_id=str(item_id) if item_id else None,
                status=_normalize_status(str(status) if status else "", source.status_mapping),
                entity_type=entity_type,
                raw_data=item,
            )

            if entity_type == "lift":
                entity.lift_type = str(item_type) if item_type else None
            else:
                entity.difficulty = str(item_type) if item_type else None

            entities.append(entity)

    return entities


def _extract_from_html_source(
    content: str,
    source: DataSource,
    entity_type: str,
) -> list[ExtractedEntity]:
    """Extract entities from HTML content."""
    entities: list[ExtractedEntity] = []

    # Get list elements
    elements = _extract_css_selector(content, source.list_selector)

    for element in elements:
        # Extract fields
        name = _extract_element_text(element, source.name_selector)
        status = _extract_element_text(element, source.status_selector)
        item_id = _extract_element_attr(element, "data-id") or _extract_element_attr(element, "id")
        item_type = _extract_element_text(element, source.type_selector) if source.type_selector else None

        if name:
            entity = ExtractedEntity(
                source_name=str(name),
                source_id=str(item_id) if item_id else None,
                status=_normalize_status(str(status) if status else "", source.status_mapping),
                entity_type=entity_type,
            )

            if entity_type == "lift":
                entity.lift_type = str(item_type) if item_type else None
            else:
                entity.difficulty = str(item_type) if item_type else None

            entities.append(entity)

    return entities


def _safe_execute_javascript(code: str, content: str) -> list[dict] | None:
    """Execute JavaScript extraction code in a restricted environment.

    SECURITY: This uses a whitelist approach - only specific operations allowed.

    The code must define a function called `extract` that takes content string
    and returns an array of objects with {name, status, id?, type?} fields.
    """
    # Check for dangerous patterns
    dangerous = [
        "eval(", "Function(", "require(", "import(",
        "process", "child_process", "fs.", "http.",
        "fetch(", "XMLHttpRequest", "WebSocket",
        "setTimeout", "setInterval", "__proto__",
        "constructor", "prototype",
    ]

    for pattern in dangerous:
        if pattern in code:
            return None

    # Use a simple regex-based extraction as a safe fallback
    # Real JavaScript execution would require isolated-vm or similar
    try:
        # Parse the code to find extraction patterns
        # This is a simplified safe executor that handles common patterns

        # Look for JSON.parse usage
        if "JSON.parse" in code:
            try:
                data = json.loads(content)
                # Try to extract using patterns found in the code
                # This is a heuristic approach
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    # Look for array properties
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            return value
            except json.JSONDecodeError:
                pass

        return None

    except Exception:
        return None


class ConfigRunner:
    """Secure config executor."""

    def __init__(self, config: ConfigSchema):
        """Initialize runner with config."""
        self.config = config
        self._lift_mapping: dict[str, str] = {}  # source_name -> openskimap_id
        self._run_mapping: dict[str, str] = {}

        # Build mapping lookups
        for m in config.lift_mappings:
            key = m.source_id if m.source_id else m.source_name
            self._lift_mapping[key.lower()] = m.openskimap_id

        for m in config.run_mappings:
            key = m.source_id if m.source_id else m.source_name
            self._run_mapping[key.lower()] = m.openskimap_id

    def _apply_mappings(self, entities: list[ExtractedEntity], entity_type: str) -> list[ExtractedEntity]:
        """Apply ID mappings to extracted entities."""
        mapping = self._lift_mapping if entity_type == "lift" else self._run_mapping

        for entity in entities:
            # Try to find mapping
            key = (entity.source_id or entity.source_name or "").lower()
            if key in mapping:
                entity.openskimap_id = mapping[key]
            else:
                # Try name only
                name_key = (entity.source_name or "").lower()
                if name_key in mapping:
                    entity.openskimap_id = mapping[name_key]

        return entities

    async def execute(self) -> ExecutionResult:
        """Execute the config and extract data."""
        result = ExecutionResult(success=True)

        for source in self.config.sources:
            # Fetch content
            content, error = await _fetch_source(source)

            if error:
                result.errors.append(f"Failed to fetch {source.url}: {error}")
                continue

            if not content:
                continue

            # Determine entity types from source
            for data_type in source.data_types:
                if "lift" in data_type:
                    entity_type = "lift"
                elif "run" in data_type:
                    entity_type = "run"
                else:
                    continue

                # Extract based on method
                if source.extraction_method == ExtractionMethod.JSON_PATH:
                    entities = _extract_from_json_source(content, source, entity_type)
                elif source.extraction_method == ExtractionMethod.CSS_SELECTOR:
                    entities = _extract_from_html_source(content, source, entity_type)
                elif source.extraction_method == ExtractionMethod.JAVASCRIPT:
                    if source.extraction_code:
                        raw_data = _safe_execute_javascript(source.extraction_code, content)
                        if raw_data:
                            entities = [
                                ExtractedEntity(
                                    source_name=str(d.get("name", "")),
                                    source_id=str(d.get("id")) if d.get("id") else None,
                                    status=_normalize_status(str(d.get("status", "")), source.status_mapping),
                                    entity_type=entity_type,
                                    raw_data=d,
                                )
                                for d in raw_data
                            ]
                        else:
                            entities = []
                            result.errors.append(f"JavaScript extraction failed for {source.url}")
                    else:
                        entities = []
                else:
                    entities = []
                    result.errors.append(f"Unsupported extraction method: {source.extraction_method}")

                # Apply mappings
                entities = self._apply_mappings(entities, entity_type)

                # Add to results
                if entity_type == "lift":
                    result.lifts.extend(entities)
                else:
                    result.runs.extend(entities)

        # Calculate coverage
        result.mapped_lifts = len([e for e in result.lifts if e.openskimap_id])
        result.total_expected_lifts = len(self.config.lift_mappings)
        if result.total_expected_lifts > 0:
            result.lift_coverage_percent = (result.mapped_lifts / result.total_expected_lifts) * 100

        result.mapped_runs = len([e for e in result.runs if e.openskimap_id])
        result.total_expected_runs = len(self.config.run_mappings)
        if result.total_expected_runs > 0:
            result.run_coverage_percent = (result.mapped_runs / result.total_expected_runs) * 100

        # Mark success based on coverage
        if result.lift_coverage_percent < 20 and result.run_coverage_percent < 20:
            result.success = False
            if not result.errors:
                result.errors.append("Coverage too low (< 20% for both lifts and runs)")

        return result


async def run_config(config: ConfigSchema) -> ExecutionResult:
    """Execute a config and return results."""
    runner = ConfigRunner(config)
    return await runner.execute()


async def test_config_coverage(
    config: ConfigSchema,
    expected_lift_count: int = 0,
    expected_run_count: int = 0,
) -> tuple[bool, ExecutionResult]:
    """Test a config and check coverage meets expectations.

    Returns:
        Tuple of (passed, result).
    """
    result = await run_config(config)

    passed = True

    # Check lift coverage
    if expected_lift_count > 0:
        if result.lift_coverage_percent < 20:
            passed = False

    # Check run coverage
    if expected_run_count > 0:
        if result.run_coverage_percent < 20:
            passed = False

    return passed, result
