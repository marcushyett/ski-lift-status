"""Scraping pipeline for extracting ski resort status data."""

from .models import (
    CapturedResource,
    ClassifiedResource,
    DataCategory,
    ExtractionConfig,
    ExtractionType,
    FieldMapping,
    NetworkCapture,
    PipelineConfig,
    PipelineResult,
    ResourceType,
    SchemaField,
    SchemaOverview,
    SourceMapping,
)
from .page_loader import PageLoader, capture_page_resources
from .classifier import ResourceClassifier, classify_network_capture
from .schema_analyzer import SchemaAnalyzer, analyze_classified_resources
from .source_mapper import SourceMapper, find_source_mappings
from .config_generator import ConfigGenerator, MockConfigGenerator, get_config_generator
from .agent import ScrapingAgent, run_scraping_agent
from .pipeline import (
    ScrapingPipeline,
    StatusPageEntry,
    load_status_pages,
    save_pipeline_config,
    load_pipeline_config,
    run_pipeline_for_resort,
    run_pipeline_for_all,
)

__all__ = [
    # Models
    "CapturedResource",
    "ClassifiedResource",
    "DataCategory",
    "ExtractionConfig",
    "ExtractionType",
    "FieldMapping",
    "NetworkCapture",
    "PipelineConfig",
    "PipelineResult",
    "ResourceType",
    "SchemaField",
    "SchemaOverview",
    "SourceMapping",
    # Page loading
    "PageLoader",
    "capture_page_resources",
    # Classification
    "ResourceClassifier",
    "classify_network_capture",
    # Schema analysis
    "SchemaAnalyzer",
    "analyze_classified_resources",
    # Source mapping
    "SourceMapper",
    "find_source_mappings",
    # Config generation
    "ConfigGenerator",
    "MockConfigGenerator",
    "get_config_generator",
    # Agent
    "ScrapingAgent",
    "run_scraping_agent",
    # Pipeline
    "ScrapingPipeline",
    "StatusPageEntry",
    "load_status_pages",
    "save_pipeline_config",
    "load_pipeline_config",
    "run_pipeline_for_resort",
    "run_pipeline_for_all",
]
