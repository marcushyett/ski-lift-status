"""Static analysis tools for identifying ski resort data in network traffic.

These tools use pattern matching and statistical analysis (not LLMs) to
identify which captured resources contain lift/run status data.
"""

from .lift_matcher import (
    LiftMatch,
    LiftMatchResult,
    find_lift_names_in_content,
    analyze_resources_for_lifts,
    load_lifts_for_resort,
)
from .run_matcher import (
    RunMatch,
    RunMatchResult,
    find_run_names_in_content,
    analyze_resources_for_runs,
    load_runs_for_resort,
)
from .status_finder import (
    StatusMatch,
    StatusFinderResult,
    LIFT_INDICATOR_WORDS,
    RUN_INDICATOR_WORDS,
    STATUS_WORDS,
    find_status_indicators,
    analyze_resources_for_status,
)
from .schema_extractor import (
    SchemaNode,
    ExtractedSchema,
    extract_json_schema,
    extract_html_schema,
    extract_schema_from_content,
)
from .sample_extractor import (
    SampleObject,
    ExtractionResult,
    extract_samples_from_json,
    extract_samples_from_html,
    extract_matching_samples,
)
from .foreign_key_detector import (
    ForeignKeyCandidate,
    ForeignKeyResult,
    detect_foreign_keys,
    find_best_foreign_key,
)
from .name_mapper import (
    NameMapping,
    MappingResult,
    map_names_to_openskimap,
    deduplicate_by_locality,
)

__all__ = [
    # Lift matching
    "LiftMatch",
    "LiftMatchResult",
    "find_lift_names_in_content",
    "analyze_resources_for_lifts",
    "load_lifts_for_resort",
    # Run matching
    "RunMatch",
    "RunMatchResult",
    "find_run_names_in_content",
    "analyze_resources_for_runs",
    "load_runs_for_resort",
    # Status finding
    "StatusMatch",
    "StatusFinderResult",
    "LIFT_INDICATOR_WORDS",
    "RUN_INDICATOR_WORDS",
    "STATUS_WORDS",
    "find_status_indicators",
    "analyze_resources_for_status",
    # Schema extraction
    "SchemaNode",
    "ExtractedSchema",
    "extract_json_schema",
    "extract_html_schema",
    "extract_schema_from_content",
    # Sample extraction
    "SampleObject",
    "ExtractionResult",
    "extract_samples_from_json",
    "extract_samples_from_html",
    "extract_matching_samples",
    # Foreign key detection
    "ForeignKeyCandidate",
    "ForeignKeyResult",
    "detect_foreign_keys",
    "find_best_foreign_key",
    # Name mapping
    "NameMapping",
    "MappingResult",
    "map_names_to_openskimap",
    "deduplicate_by_locality",
]
