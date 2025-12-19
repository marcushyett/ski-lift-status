"""Autonomous config builder module.

This module provides a fully autonomous, platform-agnostic agent for
building resort configurations. It uses AI to analyze network traffic
and generate extraction logic for ANY status page format.

Key components:
- AutonomousConfigBuilder: Main agent class
- network_capture: Browserless/Playwright traffic capture
- llm_analyzer: GPT-4o-mini based traffic analysis

Usage:
    from ski_lift_status.scraping.config_builder import (
        AutonomousConfigBuilder,
        build_config_for_resort,
        build_configs_from_csv,
    )

    # Build config for a single resort
    result = await build_config_for_resort(
        resort_id="abc123",
        resort_name="Example Resort",
        status_page_url="https://example.com/lift-status",
    )

    # Build configs from CSV file
    results = await build_configs_from_csv("data/status_pages.csv")
"""

from .agent import (
    AutonomousConfigBuilder,
    ConfigBuildResult,
    build_config_for_resort,
    build_configs_from_csv,
)
from .network_capture import (
    capture_network_traffic,
    NetworkTraffic,
    CapturedRequest,
)
from .llm_analyzer import (
    analyze_traffic,
    TrafficAnalysis,
    IdentifiedEndpoint,
)

__all__ = [
    # Main agent
    "AutonomousConfigBuilder",
    "ConfigBuildResult",
    "build_config_for_resort",
    "build_configs_from_csv",
    # Network capture
    "capture_network_traffic",
    "NetworkTraffic",
    "CapturedRequest",
    # LLM analysis
    "analyze_traffic",
    "TrafficAnalysis",
    "IdentifiedEndpoint",
]
