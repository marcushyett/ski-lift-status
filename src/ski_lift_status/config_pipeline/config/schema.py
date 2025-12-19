"""Config schema definition for ski resort status extraction.

This module defines the schema for extraction configs that can handle:
- JSON/XML APIs
- HTML with CSS selectors or XPath
- Next.js/SSR JavaScript data

The config is designed to be executed as JavaScript for NPM/Vercel deployment.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json


class LiftStatus(str, Enum):
    """Normalized lift status values."""

    OPEN = "open"
    CLOSED = "closed"
    HOLD = "hold"
    WIND_HOLD = "wind_hold"
    SCHEDULED = "scheduled"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    """Normalized run status values."""

    OPEN = "open"
    CLOSED = "closed"
    GROOMED = "groomed"
    MOGULS = "moguls"
    ICY = "icy"
    UNKNOWN = "unknown"


class ExtractionMethod(str, Enum):
    """Method used to extract data."""

    JSON_PATH = "json_path"  # JSONPath selector
    CSS_SELECTOR = "css_selector"  # CSS selector for HTML
    XPATH = "xpath"  # XPath for HTML/XML
    REGEX = "regex"  # Regular expression
    JAVASCRIPT = "javascript"  # Custom JS extraction code


@dataclass
class DataSource:
    """A data source configuration."""

    url: str
    method: str = "GET"  # HTTP method
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    content_type: str = "json"  # "json", "html", "xml", "javascript"

    # Data type this source provides
    data_types: list[str] = field(default_factory=list)  # "lift_static", "lift_dynamic", "run_static", "run_dynamic"

    # Extraction configuration
    extraction_method: ExtractionMethod = ExtractionMethod.JSON_PATH

    # Selectors based on method
    list_selector: str = ""  # Selector to get array of items
    name_selector: str = ""  # Selector for name within item
    status_selector: str = ""  # Selector for status within item
    type_selector: str = ""  # Selector for type (lift type or run difficulty)
    id_selector: str = ""  # Selector for ID within item

    # Status value mapping (source value -> normalized status)
    status_mapping: dict[str, str] = field(default_factory=dict)

    # For JavaScript extraction (custom code)
    extraction_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "url": self.url,
            "method": self.method,
            "headers": self.headers,
            "body": self.body,
            "content_type": self.content_type,
            "data_types": self.data_types,
            "extraction_method": self.extraction_method.value,
            "list_selector": self.list_selector,
            "name_selector": self.name_selector,
            "status_selector": self.status_selector,
            "type_selector": self.type_selector,
            "id_selector": self.id_selector,
            "status_mapping": self.status_mapping,
            "extraction_code": self.extraction_code,
        }


@dataclass
class NameMapping:
    """Mapping from source name/ID to OpenSkiMap ID."""

    source_name: str  # Name or ID in the data source
    source_id: str | None  # ID in the data source (if separate)
    openskimap_id: str  # OpenSkiMap ID
    openskimap_name: str  # OpenSkiMap name (for verification)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "source_id": self.source_id,
            "openskimap_id": self.openskimap_id,
            "openskimap_name": self.openskimap_name,
        }


@dataclass
class ConfigSchema:
    """Complete extraction config for a ski resort."""

    resort_id: str  # OpenSkiMap resort ID
    resort_name: str
    version: str = "1.0"

    # Data sources
    sources: list[DataSource] = field(default_factory=list)

    # Foreign key linking static and dynamic data (if separate sources)
    lift_foreign_key: str | None = None  # Field name for linking
    run_foreign_key: str | None = None

    # Name mappings to OpenSkiMap IDs
    lift_mappings: list[NameMapping] = field(default_factory=list)
    run_mappings: list[NameMapping] = field(default_factory=list)

    # Metadata
    created_at: str | None = None
    last_tested: str | None = None
    test_coverage_lifts: float = 0.0
    test_coverage_runs: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resort_id": self.resort_id,
            "resort_name": self.resort_name,
            "version": self.version,
            "sources": [s.to_dict() for s in self.sources],
            "lift_foreign_key": self.lift_foreign_key,
            "run_foreign_key": self.run_foreign_key,
            "lift_mappings": [m.to_dict() for m in self.lift_mappings],
            "run_mappings": [m.to_dict() for m in self.run_mappings],
            "created_at": self.created_at,
            "last_tested": self.last_tested,
            "test_coverage_lifts": self.test_coverage_lifts,
            "test_coverage_runs": self.test_coverage_runs,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigSchema":
        """Create from dictionary."""
        sources = []
        for s in data.get("sources", []):
            sources.append(DataSource(
                url=s.get("url", ""),
                method=s.get("method", "GET"),
                headers=s.get("headers", {}),
                body=s.get("body"),
                content_type=s.get("content_type", "json"),
                data_types=s.get("data_types", []),
                extraction_method=ExtractionMethod(s.get("extraction_method", "json_path")),
                list_selector=s.get("list_selector", ""),
                name_selector=s.get("name_selector", ""),
                status_selector=s.get("status_selector", ""),
                type_selector=s.get("type_selector", ""),
                id_selector=s.get("id_selector", ""),
                status_mapping=s.get("status_mapping", {}),
                extraction_code=s.get("extraction_code"),
            ))

        lift_mappings = [
            NameMapping(**m) for m in data.get("lift_mappings", [])
        ]
        run_mappings = [
            NameMapping(**m) for m in data.get("run_mappings", [])
        ]

        return cls(
            resort_id=data.get("resort_id", ""),
            resort_name=data.get("resort_name", ""),
            version=data.get("version", "1.0"),
            sources=sources,
            lift_foreign_key=data.get("lift_foreign_key"),
            run_foreign_key=data.get("run_foreign_key"),
            lift_mappings=lift_mappings,
            run_mappings=run_mappings,
            created_at=data.get("created_at"),
            last_tested=data.get("last_tested"),
            test_coverage_lifts=data.get("test_coverage_lifts", 0.0),
            test_coverage_runs=data.get("test_coverage_runs", 0.0),
        )


def validate_config(config: ConfigSchema) -> tuple[bool, list[str]]:
    """Validate a config schema.

    Returns:
        Tuple of (is_valid, error_messages).
    """
    errors: list[str] = []

    if not config.resort_id:
        errors.append("Missing resort_id")

    if not config.resort_name:
        errors.append("Missing resort_name")

    if not config.sources:
        errors.append("No data sources defined")

    for i, source in enumerate(config.sources):
        if not source.url:
            errors.append(f"Source {i}: Missing URL")

        if not source.data_types:
            errors.append(f"Source {i}: No data_types specified")

        if source.extraction_method == ExtractionMethod.JAVASCRIPT:
            if not source.extraction_code:
                errors.append(f"Source {i}: JavaScript extraction requires extraction_code")

            # Check for dangerous patterns in JS code
            dangerous_patterns = [
                "eval(", "Function(", "require(", "import(",
                "process.", "child_process", "fs.", "http.",
                "fetch(", "XMLHttpRequest", "WebSocket",
            ]
            if source.extraction_code:
                for pattern in dangerous_patterns:
                    if pattern in source.extraction_code:
                        errors.append(f"Source {i}: Potentially dangerous pattern '{pattern}' in extraction_code")

        elif not source.list_selector:
            errors.append(f"Source {i}: Missing list_selector for {source.extraction_method.value}")

    # Validate mappings have required fields
    for i, mapping in enumerate(config.lift_mappings):
        if not mapping.openskimap_id:
            errors.append(f"Lift mapping {i}: Missing openskimap_id")
        if not mapping.source_name and not mapping.source_id:
            errors.append(f"Lift mapping {i}: Must have source_name or source_id")

    for i, mapping in enumerate(config.run_mappings):
        if not mapping.openskimap_id:
            errors.append(f"Run mapping {i}: Missing openskimap_id")
        if not mapping.source_name and not mapping.source_id:
            errors.append(f"Run mapping {i}: Must have source_name or source_id")

    return len(errors) == 0, errors


# JSON Schema for validation (can be used with jsonschema library)
CONFIG_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["resort_id", "resort_name", "sources"],
    "properties": {
        "resort_id": {"type": "string"},
        "resort_name": {"type": "string"},
        "version": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["url", "data_types", "extraction_method"],
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string", "enum": ["GET", "POST"]},
                    "headers": {"type": "object"},
                    "body": {"type": ["string", "null"]},
                    "content_type": {"type": "string", "enum": ["json", "html", "xml", "javascript"]},
                    "data_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["lift_static", "lift_dynamic", "run_static", "run_dynamic"],
                        },
                    },
                    "extraction_method": {
                        "type": "string",
                        "enum": ["json_path", "css_selector", "xpath", "regex", "javascript"],
                    },
                    "list_selector": {"type": "string"},
                    "name_selector": {"type": "string"},
                    "status_selector": {"type": "string"},
                    "type_selector": {"type": "string"},
                    "id_selector": {"type": "string"},
                    "status_mapping": {"type": "object"},
                    "extraction_code": {"type": ["string", "null"]},
                },
            },
        },
        "lift_foreign_key": {"type": ["string", "null"]},
        "run_foreign_key": {"type": ["string", "null"]},
        "lift_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["openskimap_id"],
                "properties": {
                    "source_name": {"type": "string"},
                    "source_id": {"type": ["string", "null"]},
                    "openskimap_id": {"type": "string"},
                    "openskimap_name": {"type": "string"},
                },
            },
        },
        "run_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["openskimap_id"],
                "properties": {
                    "source_name": {"type": "string"},
                    "source_id": {"type": ["string", "null"]},
                    "openskimap_id": {"type": "string"},
                    "openskimap_name": {"type": "string"},
                },
            },
        },
    },
}
