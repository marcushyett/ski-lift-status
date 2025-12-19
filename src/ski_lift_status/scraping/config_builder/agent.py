"""Fully autonomous LangGraph agent for building resort configurations.

This agent is COMPLETELY platform-agnostic. It uses AI to analyze
network traffic and generate extraction logic for ANY status page
format, including platforms never seen before.

No hardcoded platform patterns. No manual intervention required.
"""

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

import httpx
import structlog
from langgraph.graph import END, StateGraph

from ..resort_config import ResortConfig, save_resort_config
from .network_capture import capture_network_traffic, NetworkTraffic
from .llm_analyzer import (
    analyze_traffic,
    generate_extraction_code,
    test_extraction_code,
    TrafficAnalysis,
    IdentifiedEndpoint,
)

logger = structlog.get_logger()


class BuildAction(str, Enum):
    """Actions the config builder can take."""

    CAPTURE_TRAFFIC = "capture_traffic"
    ANALYZE_TRAFFIC = "analyze_traffic"
    GENERATE_EXTRACTOR = "generate_extractor"
    TEST_EXTRACTOR = "test_extractor"
    BUILD_CONFIG = "build_config"
    VALIDATE_CONFIG = "validate_config"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class ConfigBuildResult:
    """Result of autonomous config building."""

    resort_id: str
    resort_name: str
    status_page_url: str
    success: bool
    config: ResortConfig | None = None
    platform_hint: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    validation_result: dict = field(default_factory=dict)
    extraction_code: str | None = None
    errors: list[str] = field(default_factory=list)


class BuilderState(TypedDict):
    """State for the autonomous config builder agent."""

    # Input
    resort_id: str
    resort_name: str
    status_page_url: str
    website_url: str | None

    # Capture state
    traffic: NetworkTraffic | None

    # Analysis state (LLM-driven)
    analysis: TrafficAnalysis | None
    primary_endpoint: IdentifiedEndpoint | None

    # Extraction state
    extraction_code: str | None
    extraction_result: tuple | None  # (lifts, trails)

    # Build state
    config: ResortConfig | None

    # Validation state
    validation_passed: bool
    validation_result: dict

    # Agent state
    action: BuildAction
    errors: list[str]
    is_complete: bool


async def capture_traffic_node(state: BuilderState) -> dict:
    """Capture network traffic from the status page using Browserless."""
    log = logger.bind(resort=state["resort_name"])

    try:
        log.info("capturing_traffic", url=state["status_page_url"])

        traffic = await capture_network_traffic(
            url=state["status_page_url"],
            wait_time=8000,  # Wait longer for dynamic content
            use_browserless=True,
        )

        if not traffic.requests:
            return {
                "errors": state["errors"] + ["No network requests captured"],
                "action": BuildAction.FAIL,
            }

        log.info(
            "traffic_captured",
            total_requests=len(traffic.requests),
        )

        return {
            "traffic": traffic,
            "action": BuildAction.ANALYZE_TRAFFIC,
        }

    except Exception as e:
        log.error("capture_failed", error=str(e))
        return {
            "errors": state["errors"] + [f"Traffic capture failed: {e}"],
            "action": BuildAction.FAIL,
        }


async def analyze_traffic_node(state: BuilderState) -> dict:
    """Use LLM to analyze traffic and identify status data endpoints."""
    log = logger.bind(resort=state["resort_name"])

    traffic = state["traffic"]
    if not traffic:
        return {
            "errors": state["errors"] + ["No traffic to analyze"],
            "action": BuildAction.FAIL,
        }

    log.info("analyzing_traffic_with_llm")

    analysis = await analyze_traffic(traffic)

    if not analysis.success or not analysis.primary_endpoint:
        log.warning("analysis_failed", reasoning=analysis.reasoning)
        return {
            "analysis": analysis,
            "errors": state["errors"] + [f"LLM analysis failed: {analysis.reasoning}"],
            "action": BuildAction.FAIL,
        }

    log.info(
        "analysis_complete",
        platform_hint=analysis.platform_hint,
        endpoint_count=len(analysis.endpoints),
        primary_url=analysis.primary_endpoint.url[:80],
    )

    return {
        "analysis": analysis,
        "primary_endpoint": analysis.primary_endpoint,
        "action": BuildAction.GENERATE_EXTRACTOR,
    }


async def generate_extractor_node(state: BuilderState) -> dict:
    """Generate extraction code for the identified endpoint."""
    log = logger.bind(resort=state["resort_name"])

    endpoint = state["primary_endpoint"]
    traffic = state["traffic"]

    if not endpoint or not traffic:
        return {
            "errors": state["errors"] + ["No endpoint to generate extractor for"],
            "action": BuildAction.FAIL,
        }

    # Find the response body for this endpoint
    response_body = None
    for req in traffic.requests:
        if req.url == endpoint.url:
            response_body = req.content
            break

    if not response_body:
        # Try partial URL match
        for req in traffic.requests:
            if endpoint.url in req.url or req.url in endpoint.url:
                response_body = req.content
                break

    if not response_body:
        return {
            "errors": state["errors"] + ["Could not find response body for endpoint"],
            "action": BuildAction.FAIL,
        }

    log.info("generating_extraction_code", data_format=endpoint.data_format)

    code = await generate_extraction_code(endpoint, response_body)

    if not code:
        return {
            "errors": state["errors"] + ["Failed to generate extraction code"],
            "action": BuildAction.FAIL,
        }

    log.info("extraction_code_generated", code_length=len(code))

    return {
        "extraction_code": code,
        "action": BuildAction.TEST_EXTRACTOR,
    }


async def test_extractor_node(state: BuilderState) -> dict:
    """Test the generated extraction code against captured data."""
    log = logger.bind(resort=state["resort_name"])

    code = state["extraction_code"]
    endpoint = state["primary_endpoint"]
    traffic = state["traffic"]

    if not code or not endpoint or not traffic:
        return {
            "errors": state["errors"] + ["Missing code, endpoint, or traffic for testing"],
            "action": BuildAction.FAIL,
        }

    # Find response body
    response_body = None
    for req in traffic.requests:
        if req.url == endpoint.url or endpoint.url in req.url or req.url in endpoint.url:
            response_body = req.content
            break

    if not response_body:
        return {
            "errors": state["errors"] + ["Could not find response body for testing"],
            "action": BuildAction.FAIL,
        }

    log.info("testing_extraction_code")

    result = await test_extraction_code(code, response_body)

    if not result:
        return {
            "errors": state["errors"] + ["Extraction code test failed"],
            "action": BuildAction.FAIL,
        }

    lifts, trails = result

    if not lifts and not trails:
        return {
            "errors": state["errors"] + ["Extraction returned no data"],
            "action": BuildAction.FAIL,
        }

    log.info(
        "extraction_test_passed",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return {
        "extraction_result": result,
        "action": BuildAction.BUILD_CONFIG,
    }


async def build_config_node(state: BuilderState) -> dict:
    """Build the ResortConfig from analysis results."""
    log = logger.bind(resort=state["resort_name"])

    endpoint = state["primary_endpoint"]
    analysis = state["analysis"]
    extraction_code = state["extraction_code"]

    if not endpoint or not analysis:
        return {
            "errors": state["errors"] + ["No endpoint or analysis for config"],
            "action": BuildAction.FAIL,
        }

    try:
        # Determine platform type from analysis
        platform = analysis.platform_hint or "custom"

        # Build config with extraction code for custom platforms
        config = ResortConfig(
            resort_id=state["resort_id"],
            resort_name=state["resort_name"],
            platform=platform,
            api_endpoints=[endpoint.url],
            platform_config={
                "data_format": endpoint.data_format,
                "extraction_code": extraction_code,
                "confidence": endpoint.confidence,
                "lift_selector": endpoint.lift_selector,
                "trail_selector": endpoint.trail_selector,
                "status_mapping": endpoint.status_mapping,
            },
        )

        log.info(
            "config_built",
            platform=config.platform,
            endpoint=endpoint.url[:80],
        )

        return {
            "config": config,
            "action": BuildAction.VALIDATE_CONFIG,
        }

    except Exception as e:
        log.error("config_build_failed", error=str(e))
        return {
            "errors": state["errors"] + [f"Config build failed: {e}"],
            "action": BuildAction.FAIL,
        }


async def validate_config_node(state: BuilderState) -> dict:
    """Validate the config by fetching live data."""
    log = logger.bind(resort=state["resort_name"])

    config = state["config"]
    extraction_code = state["extraction_code"]

    if not config or not extraction_code:
        return {
            "errors": state["errors"] + ["No config or extraction code to validate"],
            "action": BuildAction.FAIL,
        }

    try:
        # Fetch the endpoint directly
        url = config.api_endpoints[0] if config.api_endpoints else None
        if not url:
            return {
                "errors": state["errors"] + ["No API endpoint in config"],
                "action": BuildAction.FAIL,
            }

        log.info("validating_config", url=url[:80])

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            body = response.text

        # Run extraction
        result = await test_extraction_code(extraction_code, body)

        if not result:
            return {
                "validation_passed": False,
                "validation_result": {"error": "Extraction failed on live data"},
                "errors": state["errors"] + ["Validation failed: extraction error"],
                "action": BuildAction.FAIL,
            }

        lifts, trails = result
        lift_count = len(lifts) if lifts else 0
        trail_count = len(trails) if trails else 0

        validation_result = {
            "lift_count": lift_count,
            "trail_count": trail_count,
            "success": lift_count > 0 or trail_count > 0,
            "platform": config.platform,
        }

        if validation_result["success"]:
            log.info(
                "validation_passed",
                lift_count=lift_count,
                trail_count=trail_count,
            )
            return {
                "validation_passed": True,
                "validation_result": validation_result,
                "action": BuildAction.COMPLETE,
            }

        log.warning("validation_failed", result=validation_result)
        return {
            "validation_passed": False,
            "validation_result": validation_result,
            "errors": state["errors"] + ["Validation failed: no data extracted"],
            "action": BuildAction.FAIL,
        }

    except Exception as e:
        log.error("validation_error", error=str(e))
        return {
            "validation_passed": False,
            "validation_result": {"error": str(e)},
            "errors": state["errors"] + [f"Validation error: {e}"],
            "action": BuildAction.FAIL,
        }


def complete_node(state: BuilderState) -> dict:
    """Mark build as complete."""
    return {"is_complete": True}


def fail_node(state: BuilderState) -> dict:
    """Mark build as failed."""
    return {"is_complete": True, "config": None}


def build_config_graph() -> StateGraph:
    """Build the LangGraph for autonomous config building."""
    graph = StateGraph(BuilderState)

    # Add nodes
    graph.add_node("capture_traffic", capture_traffic_node)
    graph.add_node("analyze_traffic", analyze_traffic_node)
    graph.add_node("generate_extractor", generate_extractor_node)
    graph.add_node("test_extractor", test_extractor_node)
    graph.add_node("build_config", build_config_node)
    graph.add_node("validate_config", validate_config_node)
    graph.add_node("complete", complete_node)
    graph.add_node("fail", fail_node)

    # Add edges with routing
    graph.add_conditional_edges(
        "capture_traffic",
        lambda s: s["action"].value,
        {
            BuildAction.ANALYZE_TRAFFIC.value: "analyze_traffic",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "analyze_traffic",
        lambda s: s["action"].value,
        {
            BuildAction.GENERATE_EXTRACTOR.value: "generate_extractor",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "generate_extractor",
        lambda s: s["action"].value,
        {
            BuildAction.TEST_EXTRACTOR.value: "test_extractor",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "test_extractor",
        lambda s: s["action"].value,
        {
            BuildAction.BUILD_CONFIG.value: "build_config",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "build_config",
        lambda s: s["action"].value,
        {
            BuildAction.VALIDATE_CONFIG.value: "validate_config",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "validate_config",
        lambda s: s["action"].value,
        {
            BuildAction.COMPLETE.value: "complete",
            BuildAction.FAIL.value: "fail",
        },
    )
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    # Set entry point
    graph.set_entry_point("capture_traffic")

    return graph


class AutonomousConfigBuilder:
    """Fully autonomous agent for building resort configurations.

    This agent can handle ANY status page format without prior knowledge.
    It uses AI to analyze network traffic and generate extraction logic.
    """

    def __init__(self):
        """Initialize the autonomous config builder."""
        self.graph = build_config_graph()
        self.app = self.graph.compile()

    async def build(
        self,
        resort_id: str,
        resort_name: str,
        status_page_url: str,
        website_url: str | None = None,
    ) -> ConfigBuildResult:
        """Autonomously build a configuration for any resort.

        Args:
            resort_id: OpenSkiMap resort ID.
            resort_name: Name of the resort.
            status_page_url: URL of the status page.
            website_url: Official website URL (optional).

        Returns:
            ConfigBuildResult with built config or errors.
        """
        initial_state: BuilderState = {
            "resort_id": resort_id,
            "resort_name": resort_name,
            "status_page_url": status_page_url,
            "website_url": website_url,
            "traffic": None,
            "analysis": None,
            "primary_endpoint": None,
            "extraction_code": None,
            "extraction_result": None,
            "config": None,
            "validation_passed": False,
            "validation_result": {},
            "action": BuildAction.CAPTURE_TRAFFIC,
            "errors": [],
            "is_complete": False,
        }

        # Run the graph
        final_state = await self.app.ainvoke(initial_state)

        analysis = final_state.get("analysis")
        endpoint = final_state.get("primary_endpoint")

        return ConfigBuildResult(
            resort_id=resort_id,
            resort_name=resort_name,
            status_page_url=status_page_url,
            success=final_state["validation_passed"],
            config=final_state.get("config"),
            platform_hint=analysis.platform_hint if analysis else None,
            confidence=endpoint.confidence if endpoint else 0.0,
            reasoning=analysis.reasoning if analysis else "",
            validation_result=final_state.get("validation_result", {}),
            extraction_code=final_state.get("extraction_code"),
            errors=final_state.get("errors", []),
        )


# Convenience functions

async def build_config_for_resort(
    resort_id: str,
    resort_name: str,
    status_page_url: str,
    website_url: str | None = None,
) -> ConfigBuildResult:
    """Build config for a single resort autonomously."""
    agent = AutonomousConfigBuilder()
    return await agent.build(
        resort_id=resort_id,
        resort_name=resort_name,
        status_page_url=status_page_url,
        website_url=website_url,
    )


async def build_configs_from_csv(
    csv_path: str | Path,
    output_dir: str | Path | None = None,
    skip_existing: bool = True,
    limit: int | None = None,
) -> list[ConfigBuildResult]:
    """Build configs for all resorts in a CSV file.

    Args:
        csv_path: Path to CSV with resort_id, resort_name, status_page_url columns.
        output_dir: Directory to save configs. If None, uses default location.
        skip_existing: Skip resorts that already have configs.
        limit: Maximum number of resorts to process.

    Returns:
        List of ConfigBuildResult objects.
    """
    import asyncio
    import csv
    from ..resort_config import get_resort_config

    csv_path = Path(csv_path)
    results = []
    agent = AutonomousConfigBuilder()

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        entries = list(reader)

    if limit:
        entries = entries[:limit]

    for entry in entries:
        resort_id = entry.get("resort_id", "").strip()
        resort_name = entry.get("resort_name", "").strip()
        status_page_url = entry.get("status_page_url", "").strip()

        if not resort_id or not status_page_url:
            continue

        # Skip if config already exists
        if skip_existing and get_resort_config(resort_id):
            logger.info("skipping_existing_config", resort=resort_name)
            continue

        logger.info("building_config", resort=resort_name)

        try:
            result = await agent.build(
                resort_id=resort_id,
                resort_name=resort_name,
                status_page_url=status_page_url,
                website_url=entry.get("website_url"),
            )
            results.append(result)

            if result.success and result.config:
                # Save the config
                if output_dir:
                    path = Path(output_dir) / f"{resort_id}.json"
                    save_resort_config(result.config, path)
                else:
                    save_resort_config(result.config)

                logger.info(
                    "config_built_successfully",
                    resort=resort_name,
                    platform=result.platform_hint,
                )
            else:
                logger.warning(
                    "config_build_failed",
                    resort=resort_name,
                    errors=result.errors,
                )

        except Exception as e:
            logger.error("build_error", resort=resort_name, error=str(e))
            results.append(ConfigBuildResult(
                resort_id=resort_id,
                resort_name=resort_name,
                status_page_url=status_page_url,
                success=False,
                errors=[str(e)],
            ))

        # Rate limiting
        await asyncio.sleep(3.0)

    return results
