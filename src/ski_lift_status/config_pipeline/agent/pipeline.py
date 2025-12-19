"""LangGraph pipeline agent for automated config building.

This module implements the complete pipeline:
1. Load resort data from status_pages.csv
2. Capture network traffic
3. Run static analysis tools
4. Build analysis context
5. Generate config using GPT-5.1-Codex-Max
6. Test and iterate
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict
from enum import Enum

from langgraph.graph import END, StateGraph

from ..capture import capture_page_traffic, CapturedTraffic
from ..analysis import (
    load_lifts_for_resort,
    load_runs_for_resort,
    analyze_resources_for_lifts,
    analyze_resources_for_runs,
    analyze_resources_for_status,
    extract_schema_from_content,
    extract_matching_samples,
    extract_html_snippets,
    detect_foreign_keys,
    map_names_to_openskimap,
    deduplicate_by_locality,
)
from ..config import (
    ConfigSchema,
    run_config,
    generate_config,
    AnalysisContext,
)


class PipelineAction(str, Enum):
    """Actions in the pipeline."""

    LOAD_DATA = "load_data"
    CAPTURE_TRAFFIC = "capture_traffic"
    ANALYZE_TRAFFIC = "analyze_traffic"
    BUILD_CONTEXT = "build_context"
    GENERATE_CONFIG = "generate_config"
    TEST_CONFIG = "test_config"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class PipelineResult:
    """Result of the config pipeline."""

    resort_id: str
    resort_name: str
    success: bool
    config: ConfigSchema | None = None
    lift_coverage: float = 0.0
    run_coverage: float = 0.0
    errors: list[str] = field(default_factory=list)
    debug_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resort_id": self.resort_id,
            "resort_name": self.resort_name,
            "success": self.success,
            "config": self.config.to_dict() if self.config else None,
            "lift_coverage": self.lift_coverage,
            "run_coverage": self.run_coverage,
            "errors": self.errors,
        }


class PipelineState(TypedDict):
    """State for the pipeline."""

    # Input
    resort_id: str
    status_page_url: str
    data_dir: str

    # Loaded data
    resort_name: str
    lifts: list[dict]
    runs: list[dict]

    # Captured traffic
    traffic: CapturedTraffic | None

    # Analysis results
    lift_match_results: list[dict]
    run_match_results: list[dict]
    status_results: list[dict]
    schemas: dict[str, dict]
    samples: dict[str, list]
    foreign_keys: dict | None

    # Context for generation
    analysis_context: AnalysisContext | None

    # Generated config
    config: ConfigSchema | None
    test_result: dict | None

    # Pipeline state
    action: PipelineAction
    attempt: int
    max_attempts: int
    errors: list[str]
    is_complete: bool


def load_resort_info(resort_id: str, status_pages_csv: Path) -> tuple[str, str] | None:
    """Load resort info from status_pages.csv."""
    with open(status_pages_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("resort_id") == resort_id:
                return row.get("resort_name", ""), row.get("status_page_url", "")
    return None


async def load_data_node(state: PipelineState) -> dict:
    """Load reference data for the resort."""
    data_dir = Path(state["data_dir"])
    resort_id = state["resort_id"]

    try:
        # Load lifts
        lifts = load_lifts_for_resort(
            resort_id,
            data_dir / "lifts.csv",
        )
        lifts = deduplicate_by_locality(lifts, type_field="lift_type")

        # Load runs
        runs = load_runs_for_resort(
            resort_id,
            data_dir / "runs.csv",
        )
        runs = deduplicate_by_locality(runs, type_field="difficulty")

        # Get resort name from status_pages.csv
        info = load_resort_info(resort_id, data_dir / "status_pages.csv")
        if info:
            resort_name, status_page_url = info
        else:
            return {
                "errors": state["errors"] + [f"Resort {resort_id} not found in status_pages.csv"],
                "action": PipelineAction.FAIL,
            }

        return {
            "resort_name": resort_name,
            "status_page_url": status_page_url,
            "lifts": lifts,
            "runs": runs,
            "action": PipelineAction.CAPTURE_TRAFFIC,
        }

    except Exception as e:
        return {
            "errors": state["errors"] + [f"Failed to load data: {e}"],
            "action": PipelineAction.FAIL,
        }


async def capture_traffic_node(state: PipelineState) -> dict:
    """Capture network traffic from the status page.

    Also follows iframes that might contain lift/status data widgets
    (e.g., Lumiplan, Skiplan).
    """
    from ..capture import capture_iframe_traffic

    try:
        traffic = await capture_page_traffic(
            state["status_page_url"],
            wait_time_ms=10000,
        )

        if not traffic.resources and not traffic.page_html:
            return {
                "errors": state["errors"] + ["No resources captured"],
                "action": PipelineAction.FAIL,
            }

        # Check for iframes that might contain data widgets
        # Common providers: lumiplan, lumiplay, skiplan, skiinfo
        data_iframe_patterns = [
            "lumiplan", "lumiplay", "skiplan", "skiinfo",
            "opensnow", "snow-online", "bergfex"
        ]

        iframes_to_follow = []
        for r in traffic.resources:
            if r.method == "IFRAME":
                url_lower = r.url.lower()
                if any(pattern in url_lower for pattern in data_iframe_patterns):
                    iframes_to_follow.append(r.url)

        # Follow data iframes and merge their resources
        for iframe_url in iframes_to_follow[:2]:  # Limit to 2 iframes
            try:
                # Retry iframe capture up to 3 times if we get partial HTML
                # Some providers like Skiplan need the page to fully render
                iframe_traffic = None
                for retry in range(3):
                    import asyncio as aio
                    if retry > 0:
                        await aio.sleep(2)  # Wait before retry

                    iframe_traffic = await capture_iframe_traffic(
                        iframe_url,
                        state["status_page_url"],
                    )

                    # Check if we got enough content (>800KB suggests full load)
                    if iframe_traffic.page_html and len(iframe_traffic.page_html) > 800000:
                        break

                if not iframe_traffic:
                    continue

                # Add iframe's page HTML as a resource for analysis
                # This is critical for providers like Skiplan that render HTML
                # instead of using JSON APIs
                if iframe_traffic.page_html and len(iframe_traffic.page_html) > 1000:
                    from ..capture import CapturedResource, ResourceType
                    html_resource = CapturedResource(
                        url=iframe_url,
                        method="GET",
                        resource_type=ResourceType.HTML,
                        content_type="text/html",
                        status_code=200,
                        request_headers={},
                        response_headers={},
                        body=iframe_traffic.page_html,
                        body_size=len(iframe_traffic.page_html),
                    )
                    traffic.resources.append(html_resource)

                # Also add any XHR resources from the iframe
                if iframe_traffic.resources:
                    for r in iframe_traffic.resources:
                        if r.body and len(r.body) > 50:
                            traffic.resources.append(r)
            except Exception as e:
                # Log but continue
                pass

        # Add main page HTML as a resource if it contains status data
        # This is important for SSR sites like cervinia.it that don't use XHR
        if traffic.page_html and len(traffic.page_html) > 10000:
            html_lower = traffic.page_html.lower()
            # Check if page contains status indicators
            status_indicators = (
                html_lower.count("open") + html_lower.count("closed") +
                html_lower.count("ouvert") + html_lower.count("fermé") +
                html_lower.count("aperto") + html_lower.count("chiuso") +
                html_lower.count("geöffnet") + html_lower.count("geschlossen")
            )
            if status_indicators > 5:
                from ..capture import CapturedResource, ResourceType
                page_resource = CapturedResource(
                    url=state["status_page_url"],
                    method="GET",
                    resource_type=ResourceType.HTML,
                    content_type="text/html",
                    status_code=200,
                    request_headers={},
                    response_headers={},
                    body=traffic.page_html,
                    body_size=len(traffic.page_html),
                )
                traffic.resources.append(page_resource)

        return {
            "traffic": traffic,
            "action": PipelineAction.ANALYZE_TRAFFIC,
        }

    except Exception as e:
        return {
            "errors": state["errors"] + [f"Traffic capture failed: {e}"],
            "action": PipelineAction.FAIL,
        }


async def analyze_traffic_node(state: PipelineState) -> dict:
    """Run static analysis on captured traffic."""
    traffic = state["traffic"]
    lifts = state["lifts"]
    runs = state["runs"]

    if not traffic:
        return {
            "errors": state["errors"] + ["No traffic to analyze"],
            "action": PipelineAction.FAIL,
        }

    # Convert resources to dict format for analysis
    resources = [r.to_dict() for r in traffic.resources if r.body]

    # Analyze for lift names
    lift_names = [l.get("name", "") for l in lifts if l.get("name")]
    lift_results = analyze_resources_for_lifts(resources, lifts)

    # Analyze for run names
    run_names = [r.get("name", "") for r in runs if r.get("name")]
    run_results = analyze_resources_for_runs(resources, runs)

    # Analyze for status indicators
    status_results = analyze_resources_for_status(resources)

    # Extract schemas from top resources
    schemas = {}
    samples = {}

    # Best lift resource
    if lift_results and lift_results[0].coverage_percent > 0:
        best_lift_url = lift_results[0].resource_url
        for r in resources:
            if r.get("url") == best_lift_url:
                schemas["lift"] = extract_schema_from_content(
                    r.get("body", ""),
                    r.get("content_type"),
                ).to_dict()
                sample_result = extract_matching_samples(
                    r.get("body", ""),
                    r.get("content_type"),
                    lift_names,
                    run_names,
                )
                samples["lift"] = [s.to_dict() for s in sample_result.samples]
                break

    # Best run resource
    if run_results and run_results[0].coverage_percent > 0:
        best_run_url = run_results[0].resource_url
        for r in resources:
            if r.get("url") == best_run_url:
                schemas["run"] = extract_schema_from_content(
                    r.get("body", ""),
                    r.get("content_type"),
                ).to_dict()
                if "lift" not in samples or best_run_url != lift_results[0].resource_url:
                    sample_result = extract_matching_samples(
                        r.get("body", ""),
                        r.get("content_type"),
                        lift_names,
                        run_names,
                    )
                    samples["run"] = [s.to_dict() for s in sample_result.samples]
                break

    # Detect foreign keys if we have multiple data sources
    foreign_keys = None
    if lift_results and len(lift_results) >= 2:
        r1 = next((r for r in resources if r.get("url") == lift_results[0].resource_url), None)
        r2 = next((r for r in resources if r.get("url") == lift_results[1].resource_url), None)
        if r1 and r2 and r1.get("body") and r2.get("body"):
            fk_result = detect_foreign_keys(
                r1["body"],
                r2["body"],
                r1["url"],
                r2["url"],
            )
            if fk_result.best_candidate:
                foreign_keys = fk_result.to_dict()

    return {
        "lift_match_results": [r.to_dict() for r in lift_results[:5]],
        "run_match_results": [r.to_dict() for r in run_results[:5]],
        "status_results": [r.to_dict() for r in status_results[:5]],
        "schemas": schemas,
        "samples": samples,
        "foreign_keys": foreign_keys,
        "action": PipelineAction.BUILD_CONTEXT,
    }


async def build_context_node(state: PipelineState) -> dict:
    """Build analysis context for config generation."""
    traffic = state["traffic"]
    lifts = state["lifts"]
    runs = state["runs"]

    if not traffic:
        return {
            "errors": state["errors"] + ["No traffic for context"],
            "action": PipelineAction.FAIL,
        }

    resources = [r.to_dict() for r in traffic.resources if r.body]

    # Map online names to OpenSkiMap IDs
    # First, extract names from best resources
    lift_online_names = []
    run_online_names = []

    lift_results = state.get("lift_match_results", [])
    run_results = state.get("run_match_results", [])

    if lift_results:
        for match in lift_results[0].get("matches", []):
            lift_online_names.append(match.get("matched_text", ""))

    if run_results:
        for match in run_results[0].get("matches", []):
            run_online_names.append(match.get("matched_text", ""))

    # Map to OpenSkiMap
    lift_mapping_result = map_names_to_openskimap(
        lift_online_names,
        lifts,
        entity_type="lift",
    )
    run_mapping_result = map_names_to_openskimap(
        run_online_names,
        runs,
        entity_type="run",
    )

    # Build context
    context = AnalysisContext(
        resort_id=state["resort_id"],
        resort_name=state["resort_name"],
    )

    # Set best URLs
    if lift_results:
        context.lift_dynamic_url = lift_results[0].get("resource_url")
        context.lift_coverage = lift_results[0].get("coverage_percent", 0)

    if run_results:
        context.run_dynamic_url = run_results[0].get("resource_url")
        context.run_coverage = run_results[0].get("coverage_percent", 0)

    # Set schemas and samples
    context.lift_dynamic_schema = state.get("schemas", {}).get("lift")
    context.run_dynamic_schema = state.get("schemas", {}).get("run")
    context.lift_samples = state.get("samples", {}).get("lift", [])[:5]
    context.run_samples = state.get("samples", {}).get("run", [])[:5]

    # Extract HTML snippets from best lift resource for CSS selector generation
    lift_names = [l.get("name", "") for l in lifts if l.get("name")]
    run_names = [r.get("name", "") for r in runs if r.get("name")]

    if lift_results:
        best_url = lift_results[0].get("resource_url")
        for r in resources:
            if r.get("url") == best_url and r.get("body"):
                content_type = r.get("content_type", "")
                if "html" in content_type.lower() or not content_type:
                    snippets = extract_html_snippets(
                        r["body"],
                        lift_names,
                        run_names,
                        max_samples=3,
                    )
                    context.html_snippets = snippets
                break

    # Set foreign keys
    fk = state.get("foreign_keys")
    if fk and fk.get("best_candidate"):
        context.lift_foreign_key = fk["best_candidate"].get("source_field")

    # Set mappings
    context.lift_mappings = [m.to_dict() for m in lift_mapping_result.mappings]
    context.run_mappings = [m.to_dict() for m in run_mapping_result.mappings]

    return {
        "analysis_context": context,
        "action": PipelineAction.GENERATE_CONFIG,
    }


async def generate_config_node(state: PipelineState) -> dict:
    """Generate config using GPT-5.1-Codex-Max."""
    context = state.get("analysis_context")

    if not context:
        return {
            "errors": state["errors"] + ["No analysis context"],
            "action": PipelineAction.FAIL,
        }

    result = await generate_config(context, max_attempts=1)

    if result.success and result.config:
        return {
            "config": result.config,
            "action": PipelineAction.TEST_CONFIG,
        }
    else:
        return {
            "errors": state["errors"] + result.errors,
            "action": PipelineAction.FAIL,
        }


async def test_config_node(state: PipelineState) -> dict:
    """Test the generated config against captured content.

    Uses cached content from traffic capture to test configs that require
    JavaScript-rendered HTML (e.g., Skiplan, Lumiplan widgets).
    """
    config = state.get("config")
    traffic = state.get("traffic")

    if not config:
        return {
            "errors": state["errors"] + ["No config to test"],
            "action": PipelineAction.FAIL,
        }

    # Build cached content map from captured traffic
    # This allows testing against JavaScript-rendered HTML
    cached_content: dict[str, str] = {}
    if traffic:
        for r in traffic.resources:
            if r.body and len(r.body) > 100:
                cached_content[r.url] = r.body

    try:
        result = await run_config(config, cached_content=cached_content)

        test_result = result.to_dict()

        # Check if coverage is acceptable (>= 20%)
        if result.lift_coverage_percent >= 20 or result.run_coverage_percent >= 20:
            return {
                "test_result": test_result,
                "action": PipelineAction.COMPLETE,
            }

        # If not, check if we should retry
        attempt = state.get("attempt", 0) + 1
        max_attempts = state.get("max_attempts", 3)

        if attempt < max_attempts:
            return {
                "test_result": test_result,
                "attempt": attempt,
                "errors": state["errors"] + [f"Coverage too low: lifts={result.lift_coverage_percent:.1f}%, runs={result.run_coverage_percent:.1f}%"],
                "action": PipelineAction.GENERATE_CONFIG,  # Retry
            }
        else:
            return {
                "test_result": test_result,
                "errors": state["errors"] + ["Max attempts reached with insufficient coverage"],
                "action": PipelineAction.FAIL,
            }

    except Exception as e:
        return {
            "errors": state["errors"] + [f"Config test failed: {e}"],
            "action": PipelineAction.FAIL,
        }


def complete_node(state: PipelineState) -> dict:
    """Mark pipeline as complete."""
    return {"is_complete": True}


def fail_node(state: PipelineState) -> dict:
    """Mark pipeline as failed."""
    return {"is_complete": True, "config": None}


def build_pipeline_graph() -> StateGraph:
    """Build the LangGraph pipeline."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("load_data", load_data_node)
    graph.add_node("capture_traffic", capture_traffic_node)
    graph.add_node("analyze_traffic", analyze_traffic_node)
    graph.add_node("build_context", build_context_node)
    graph.add_node("generate_config", generate_config_node)
    graph.add_node("test_config", test_config_node)
    graph.add_node("complete", complete_node)
    graph.add_node("fail", fail_node)

    # Add edges
    graph.add_conditional_edges(
        "load_data",
        lambda s: s["action"].value,
        {
            PipelineAction.CAPTURE_TRAFFIC.value: "capture_traffic",
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "capture_traffic",
        lambda s: s["action"].value,
        {
            PipelineAction.ANALYZE_TRAFFIC.value: "analyze_traffic",
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "analyze_traffic",
        lambda s: s["action"].value,
        {
            PipelineAction.BUILD_CONTEXT.value: "build_context",
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "build_context",
        lambda s: s["action"].value,
        {
            PipelineAction.GENERATE_CONFIG.value: "generate_config",
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "generate_config",
        lambda s: s["action"].value,
        {
            PipelineAction.TEST_CONFIG.value: "test_config",
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_conditional_edges(
        "test_config",
        lambda s: s["action"].value,
        {
            PipelineAction.COMPLETE.value: "complete",
            PipelineAction.GENERATE_CONFIG.value: "generate_config",  # Retry loop
            PipelineAction.FAIL.value: "fail",
        },
    )
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    # Set entry point
    graph.set_entry_point("load_data")

    return graph


class ConfigPipelineAgent:
    """Agent for running the config pipeline."""

    def __init__(self, data_dir: str | Path = "data"):
        """Initialize the agent."""
        self.data_dir = str(data_dir)
        self.graph = build_pipeline_graph()
        self.app = self.graph.compile()

    async def run(
        self,
        resort_id: str,
        max_attempts: int = 3,
    ) -> PipelineResult:
        """Run the pipeline for a resort.

        Args:
            resort_id: OpenSkiMap resort ID.
            max_attempts: Maximum config generation attempts.

        Returns:
            PipelineResult with config or errors.
        """
        initial_state: PipelineState = {
            "resort_id": resort_id,
            "status_page_url": "",
            "data_dir": self.data_dir,
            "resort_name": "",
            "lifts": [],
            "runs": [],
            "traffic": None,
            "lift_match_results": [],
            "run_match_results": [],
            "status_results": [],
            "schemas": {},
            "samples": {},
            "foreign_keys": None,
            "analysis_context": None,
            "config": None,
            "test_result": None,
            "action": PipelineAction.LOAD_DATA,
            "attempt": 0,
            "max_attempts": max_attempts,
            "errors": [],
            "is_complete": False,
        }

        # Run the pipeline
        final_state = await self.app.ainvoke(initial_state)

        # Build result
        test_result = final_state.get("test_result") or {}

        return PipelineResult(
            resort_id=resort_id,
            resort_name=final_state.get("resort_name", ""),
            success=final_state.get("config") is not None and final_state.get("is_complete", False),
            config=final_state.get("config"),
            lift_coverage=test_result.get("lift_coverage_percent", 0) if test_result else 0,
            run_coverage=test_result.get("run_coverage_percent", 0) if test_result else 0,
            errors=final_state.get("errors", []),
            debug_info={
                "attempts": final_state.get("attempt", 0),
                "lift_match_results": final_state.get("lift_match_results", [])[:2],
                "run_match_results": final_state.get("run_match_results", [])[:2],
            },
        )


async def run_pipeline(
    resort_id: str,
    data_dir: str | Path = "data",
    max_attempts: int = 3,
) -> PipelineResult:
    """Run the config pipeline for a resort.

    This is the main entry point for automated config generation.

    Args:
        resort_id: OpenSkiMap resort ID.
        data_dir: Directory containing CSV data files.
        max_attempts: Maximum config generation attempts.

    Returns:
        PipelineResult with generated config or errors.
    """
    agent = ConfigPipelineAgent(data_dir=data_dir)
    return await agent.run(resort_id, max_attempts=max_attempts)
