"""Data models for the scraping pipeline."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Type of captured network resource."""

    XHR = "xhr"
    JAVASCRIPT = "javascript"
    HTML = "html"
    JSON = "json"
    OTHER = "other"


class DataCategory(str, Enum):
    """Category of data contained in a resource."""

    STATIC_METADATA = "static_metadata"  # Names, types, identifiers
    DYNAMIC_STATUS = "dynamic_status"  # Operational status, queue lengths, conditions
    MIXED = "mixed"  # Contains both static and dynamic data
    UNKNOWN = "unknown"


class ExtractionType(str, Enum):
    """Type of extraction method to use."""

    JSON_PATH = "json_path"
    CSS_SELECTOR = "css_selector"
    XPATH = "xpath"
    REGEX = "regex"


class CapturedResource(BaseModel):
    """A network resource captured during page load."""

    url: str
    resource_type: ResourceType
    content_type: str | None = None
    content: str
    size_bytes: int
    response_status: int
    headers: dict[str, str] = Field(default_factory=dict)


class NetworkCapture(BaseModel):
    """All network traffic captured during page load."""

    resort_id: str
    status_page_url: str
    resources: list[CapturedResource] = Field(default_factory=list)
    page_html: str | None = None
    load_time_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)


class ClassifiedResource(BaseModel):
    """A resource with classification metadata."""

    resource: CapturedResource
    category: DataCategory
    lift_coverage: float = 0.0  # Percentage of lifts mentioned
    run_coverage: float = 0.0  # Percentage of runs mentioned
    matched_lift_names: list[str] = Field(default_factory=list)
    matched_run_names: list[str] = Field(default_factory=list)
    contains_status_keywords: bool = False
    confidence_score: float = 0.0


class SchemaField(BaseModel):
    """A field in a data schema."""

    name: str
    field_type: str  # e.g., "string", "number", "boolean", "array", "object"
    sample_values: list[Any] = Field(default_factory=list)
    is_identifier: bool = False
    is_status_field: bool = False
    is_name_field: bool = False


class SchemaOverview(BaseModel):
    """Overview of a data structure's schema."""

    resource_url: str
    category: DataCategory
    fields: list[SchemaField] = Field(default_factory=list)
    sample_objects: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    total_objects_count: int = 0
    root_path: str | None = None  # JSON path to the array of objects


class FieldMapping(BaseModel):
    """Mapping between source field and target field."""

    source_field: str
    target_field: str
    transformation: str | None = None  # Optional transformation expression


class SourceMapping(BaseModel):
    """Mapping between static and dynamic data sources."""

    static_resource_url: str
    dynamic_resource_url: str
    join_key_static: str  # Field name in static resource
    join_key_dynamic: str  # Field name in dynamic resource
    match_type: str = "exact"  # "exact", "fuzzy", "contains"
    confidence_score: float = 0.0


class ExtractionConfig(BaseModel):
    """Configuration for extracting data from a resource."""

    resource_url: str
    extraction_type: ExtractionType
    category: DataCategory

    # Extraction selectors/paths
    root_selector: str | None = None  # Path to array of items
    field_mappings: list[FieldMapping] = Field(default_factory=list)

    # For lifts
    lift_name_selector: str | None = None
    lift_status_selector: str | None = None
    lift_type_selector: str | None = None
    lift_id_selector: str | None = None

    # For runs
    run_name_selector: str | None = None
    run_status_selector: str | None = None
    run_difficulty_selector: str | None = None
    run_id_selector: str | None = None

    # Validation
    expected_item_count: int | None = None
    validation_regex: str | None = None


class PipelineConfig(BaseModel):
    """Configuration for the entire scraping pipeline."""

    resort_id: str
    resort_name: str
    status_page_url: str

    # Extraction configs for different data sources
    extraction_configs: list[ExtractionConfig] = Field(default_factory=list)

    # Source mappings for cross-referencing
    source_mappings: list[SourceMapping] = Field(default_factory=list)

    # Coverage metrics
    lift_coverage: float = 0.0
    run_coverage: float = 0.0

    # Validation
    is_validated: bool = False
    validation_errors: list[str] = Field(default_factory=list)

    # Generation metadata
    generated_at: str | None = None
    generation_attempts: int = 0


class PipelineResult(BaseModel):
    """Result of running the scraping pipeline."""

    resort_id: str
    success: bool
    config: PipelineConfig | None = None

    # Extracted data
    lifts_data: list[dict[str, Any]] = Field(default_factory=list)
    runs_data: list[dict[str, Any]] = Field(default_factory=list)

    # Metrics
    lift_coverage: float = 0.0
    run_coverage: float = 0.0

    # Debugging info
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    debug_info: dict[str, Any] = Field(default_factory=dict)
