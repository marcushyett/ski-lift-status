"""Config pipeline for automated ski resort status extraction.

This module provides a complete pipeline for building extraction configs:

1. **Capture** - Network traffic capture using Playwright/Browserless
2. **Analysis** - Static tools for finding lift/run data in responses
3. **Config** - Schema definition, secure runner, and generation
4. **Agent** - LangGraph orchestration for the complete pipeline

## Quick Start

```python
from ski_lift_status.config_pipeline import run_pipeline

# Run the complete pipeline for a resort
result = await run_pipeline(
    resort_id="abc123",
    data_dir="data",
)

if result.success:
    print(f"Config generated with {result.lift_coverage:.1f}% lift coverage")
    config = result.config
else:
    print(f"Failed: {result.errors}")
```

## Manual Analysis

For more control, use the individual analysis tools:

```python
from ski_lift_status.config_pipeline.capture import capture_page_traffic
from ski_lift_status.config_pipeline.analysis import (
    analyze_resources_for_lifts,
    analyze_resources_for_runs,
    find_status_indicators,
)

# Capture traffic
traffic = await capture_page_traffic("https://example.com/lift-status")

# Analyze
resources = [r.to_dict() for r in traffic.resources if r.body]
lift_results = analyze_resources_for_lifts(resources, lifts)
```
"""

from .capture import (
    CapturedResource,
    ResourceType,
    CapturedTraffic,
    capture_page_traffic,
)
from .analysis import (
    # Lift matching
    LiftMatch,
    LiftMatchResult,
    find_lift_names_in_content,
    analyze_resources_for_lifts,
    # Run matching
    RunMatch,
    RunMatchResult,
    find_run_names_in_content,
    analyze_resources_for_runs,
    # Status finding
    StatusMatch,
    StatusFinderResult,
    find_status_indicators,
    analyze_resources_for_status,
    # Schema extraction
    SchemaNode,
    ExtractedSchema,
    extract_schema_from_content,
    # Sample extraction
    SampleObject,
    ExtractionResult,
    extract_matching_samples,
    # Foreign key detection
    ForeignKeyCandidate,
    ForeignKeyResult,
    detect_foreign_keys,
    # Name mapping
    NameMapping,
    MappingResult,
    map_names_to_openskimap,
)
from .config import (
    ConfigSchema,
    DataSource,
    ExtractionMethod,
    LiftStatus,
    RunStatus,
    run_config,
    generate_config,
)
from .agent import (
    ConfigPipelineAgent,
    PipelineResult,
    run_pipeline,
)

__all__ = [
    # Capture
    "CapturedResource",
    "ResourceType",
    "CapturedTraffic",
    "capture_page_traffic",
    # Analysis
    "LiftMatch",
    "LiftMatchResult",
    "find_lift_names_in_content",
    "analyze_resources_for_lifts",
    "RunMatch",
    "RunMatchResult",
    "find_run_names_in_content",
    "analyze_resources_for_runs",
    "StatusMatch",
    "StatusFinderResult",
    "find_status_indicators",
    "analyze_resources_for_status",
    "SchemaNode",
    "ExtractedSchema",
    "extract_schema_from_content",
    "SampleObject",
    "ExtractionResult",
    "extract_matching_samples",
    "ForeignKeyCandidate",
    "ForeignKeyResult",
    "detect_foreign_keys",
    "NameMapping",
    "MappingResult",
    "map_names_to_openskimap",
    # Config
    "ConfigSchema",
    "DataSource",
    "ExtractionMethod",
    "LiftStatus",
    "RunStatus",
    "run_config",
    "generate_config",
    # Agent
    "ConfigPipelineAgent",
    "PipelineResult",
    "run_pipeline",
]
