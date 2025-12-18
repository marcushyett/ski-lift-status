"""LangGraph-based agent for iterative config refinement."""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict

from jsonpath_ng import parse as jsonpath_parse
from langgraph.graph import END, StateGraph

from ..models import Lift, Run
from .models import (
    ExtractionType,
    PipelineConfig,
    PipelineResult,
    SchemaOverview,
)


class AgentAction(str, Enum):
    """Actions the agent can take."""

    EXTRACT_DATA = "extract_data"
    VALIDATE_COVERAGE = "validate_coverage"
    REFINE_CONFIG = "refine_config"
    DEBUG_FAILURE = "debug_failure"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class DebugInfo:
    """Debug information for a failed extraction."""

    selector: str
    error: str
    sample_content: str | None = None
    suggestion: str | None = None


class AgentState(TypedDict):
    """State for the LangGraph agent."""

    config: PipelineConfig
    schemas: list[SchemaOverview]
    sample_contents: dict[str, str]
    reference_lifts: list[dict]
    reference_runs: list[dict]

    # Results
    extracted_lifts: list[dict[str, Any]]
    extracted_runs: list[dict[str, Any]]
    lift_coverage: float
    run_coverage: float

    # Agent state
    attempt: int
    max_attempts: int
    min_coverage: float
    errors: list[str]
    debug_info: list[DebugInfo]
    action: AgentAction
    is_complete: bool


# Coverage threshold from issue requirements
DEFAULT_MIN_COVERAGE = 0.20  # 20%
DEFAULT_MAX_ATTEMPTS = 3


def _extract_with_jsonpath(content: str, selector: str) -> list[Any]:
    """Extract data using JSONPath."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    try:
        expression = jsonpath_parse(selector)
        matches = expression.find(data)
        return [match.value for match in matches]
    except Exception:
        return []


def _extract_with_css(content: str, selector: str) -> list[str]:
    """Extract data using CSS selector."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "html.parser")
        elements = soup.select(selector)
        return [elem.get_text(strip=True) for elem in elements]
    except Exception:
        return []


def _extract_field(
    content: str,
    selector: str | None,
    extraction_type: ExtractionType,
) -> list[Any]:
    """Extract a field from content using the appropriate method."""
    if not selector:
        return []

    if extraction_type == ExtractionType.JSON_PATH:
        return _extract_with_jsonpath(content, selector)
    elif extraction_type == ExtractionType.CSS_SELECTOR:
        return _extract_with_css(content, selector)
    elif extraction_type == ExtractionType.XPATH:
        # XPath support via lxml
        try:
            from lxml import html
            tree = html.fromstring(content)
            elements = tree.xpath(selector)
            return [
                elem.text_content().strip() if hasattr(elem, "text_content") else str(elem)
                for elem in elements
            ]
        except Exception:
            return []
    elif extraction_type == ExtractionType.REGEX:
        try:
            matches = re.findall(selector, content)
            return matches
        except Exception:
            return []

    return []


def _calculate_coverage(
    extracted_names: list[str],
    reference_names: list[str],
) -> tuple[float, list[str]]:
    """Calculate what percentage of reference names were extracted."""
    if not reference_names:
        return 0.0, []

    # Normalize names for comparison
    normalized_extracted = {n.lower().strip() for n in extracted_names if n}
    matched = []

    for ref_name in reference_names:
        if not ref_name:
            continue
        ref_lower = ref_name.lower().strip()

        # Check for exact or partial match
        if ref_lower in normalized_extracted:
            matched.append(ref_name)
            continue

        # Check if any extracted name contains reference or vice versa
        for ext in normalized_extracted:
            if ref_lower in ext or ext in ref_lower:
                matched.append(ref_name)
                break

    coverage = len(matched) / len(reference_names)
    return coverage, matched


def extract_data(state: AgentState) -> AgentState:
    """Extract data using the current configuration."""
    config = state["config"]
    sample_contents = state["sample_contents"]
    extracted_lifts = []
    extracted_runs = []
    errors = []

    for extraction_config in config.extraction_configs:
        content = sample_contents.get(extraction_config.resource_url, "")
        if not content:
            errors.append(f"No content for {extraction_config.resource_url}")
            continue

        extraction_type = extraction_config.extraction_type

        # Extract lift data
        if extraction_config.lift_name_selector:
            names = _extract_field(content, extraction_config.lift_name_selector, extraction_type)
            statuses = _extract_field(content, extraction_config.lift_status_selector, extraction_type)
            types = _extract_field(content, extraction_config.lift_type_selector, extraction_type)
            ids = _extract_field(content, extraction_config.lift_id_selector, extraction_type)

            for i, name in enumerate(names):
                lift = {
                    "name": name,
                    "status": statuses[i] if i < len(statuses) else None,
                    "type": types[i] if i < len(types) else None,
                    "id": ids[i] if i < len(ids) else None,
                }
                extracted_lifts.append(lift)

        # Extract run data
        if extraction_config.run_name_selector:
            names = _extract_field(content, extraction_config.run_name_selector, extraction_type)
            statuses = _extract_field(content, extraction_config.run_status_selector, extraction_type)
            difficulties = _extract_field(content, extraction_config.run_difficulty_selector, extraction_type)
            ids = _extract_field(content, extraction_config.run_id_selector, extraction_type)

            for i, name in enumerate(names):
                run = {
                    "name": name,
                    "status": statuses[i] if i < len(statuses) else None,
                    "difficulty": difficulties[i] if i < len(difficulties) else None,
                    "id": ids[i] if i < len(ids) else None,
                }
                extracted_runs.append(run)

    return {
        **state,
        "extracted_lifts": extracted_lifts,
        "extracted_runs": extracted_runs,
        "errors": state["errors"] + errors,
        "action": AgentAction.VALIDATE_COVERAGE,
    }


def validate_coverage(state: AgentState) -> AgentState:
    """Validate extraction coverage against reference data."""
    extracted_lift_names = [lift.get("name", "") for lift in state["extracted_lifts"]]
    extracted_run_names = [run.get("name", "") for run in state["extracted_runs"]]

    reference_lift_names = [lift.get("name", "") for lift in state["reference_lifts"]]
    reference_run_names = [r.get("name", "") for r in state["reference_runs"]]

    lift_coverage, _ = _calculate_coverage(extracted_lift_names, reference_lift_names)
    run_coverage, _ = _calculate_coverage(extracted_run_names, reference_run_names)

    # Determine next action
    min_coverage = state["min_coverage"]
    meets_threshold = lift_coverage >= min_coverage or run_coverage >= min_coverage

    if meets_threshold:
        action = AgentAction.COMPLETE
    elif state["attempt"] >= state["max_attempts"]:
        action = AgentAction.FAIL
    else:
        action = AgentAction.DEBUG_FAILURE

    return {
        **state,
        "lift_coverage": lift_coverage,
        "run_coverage": run_coverage,
        "action": action,
    }


def debug_failure(state: AgentState) -> AgentState:
    """Analyze extraction failures and generate debug info."""
    debug_info = []
    config = state["config"]
    sample_contents = state["sample_contents"]

    for extraction_config in config.extraction_configs:
        content = sample_contents.get(extraction_config.resource_url, "")

        # Check each selector
        selectors = [
            ("lift_name", extraction_config.lift_name_selector),
            ("lift_status", extraction_config.lift_status_selector),
            ("run_name", extraction_config.run_name_selector),
            ("run_status", extraction_config.run_status_selector),
        ]

        for field_name, selector in selectors:
            if not selector:
                continue

            results = _extract_field(content, selector, extraction_config.extraction_type)

            if not results:
                debug = DebugInfo(
                    selector=selector,
                    error=f"Selector '{selector}' returned no results for {field_name}",
                    sample_content=content[:500] if content else None,
                    suggestion=f"Try a different selector pattern for {field_name}",
                )
                debug_info.append(debug)

    return {
        **state,
        "debug_info": debug_info,
        "action": AgentAction.REFINE_CONFIG,
    }


def refine_config(state: AgentState) -> AgentState:
    """Refine the configuration based on debug info."""
    # Increment attempt counter
    new_attempt = state["attempt"] + 1

    # For now, simple refinement: try alternative selectors
    config = state["config"]
    config.generation_attempts = new_attempt

    # Mark for re-extraction
    return {
        **state,
        "attempt": new_attempt,
        "config": config,
        "action": AgentAction.EXTRACT_DATA,
    }


def complete(state: AgentState) -> AgentState:
    """Mark the pipeline as successfully complete."""
    return {
        **state,
        "is_complete": True,
        "action": AgentAction.COMPLETE,
    }


def fail(state: AgentState) -> AgentState:
    """Mark the pipeline as failed."""
    state["errors"].append(
        f"Failed after {state['attempt']} attempts. "
        f"Coverage: lifts={state['lift_coverage']:.1%}, runs={state['run_coverage']:.1%}"
    )
    return {
        **state,
        "is_complete": True,
        "action": AgentAction.FAIL,
    }


def route_action(state: AgentState) -> str:
    """Route to the next node based on current action."""
    action = state["action"]

    if action == AgentAction.EXTRACT_DATA:
        return "extract_data"
    elif action == AgentAction.VALIDATE_COVERAGE:
        return "validate_coverage"
    elif action == AgentAction.DEBUG_FAILURE:
        return "debug_failure"
    elif action == AgentAction.REFINE_CONFIG:
        return "refine_config"
    elif action == AgentAction.COMPLETE:
        return "complete"
    elif action == AgentAction.FAIL:
        return "fail"
    else:
        return END


def should_continue(state: AgentState) -> str:
    """Determine if the agent should continue or end."""
    if state["is_complete"]:
        return END
    return "router"


def build_agent_graph() -> StateGraph:
    """Build the LangGraph agent for config refinement."""
    # Create the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("extract_data", extract_data)
    graph.add_node("validate_coverage", validate_coverage)
    graph.add_node("debug_failure", debug_failure)
    graph.add_node("refine_config", refine_config)
    graph.add_node("complete", complete)
    graph.add_node("fail", fail)

    # Add edges
    graph.add_edge("extract_data", "validate_coverage")
    graph.add_conditional_edges(
        "validate_coverage",
        lambda s: s["action"].value,
        {
            AgentAction.COMPLETE.value: "complete",
            AgentAction.FAIL.value: "fail",
            AgentAction.DEBUG_FAILURE.value: "debug_failure",
        },
    )
    graph.add_edge("debug_failure", "refine_config")
    graph.add_edge("refine_config", "extract_data")
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    # Set entry point
    graph.set_entry_point("extract_data")

    return graph


class ScrapingAgent:
    """Agent for iterative config refinement and data extraction."""

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        min_coverage: float = DEFAULT_MIN_COVERAGE,
    ):
        """Initialize the scraping agent.

        Args:
            max_attempts: Maximum refinement attempts.
            min_coverage: Minimum coverage threshold (default 20%).
        """
        self.max_attempts = max_attempts
        self.min_coverage = min_coverage
        self.graph = build_agent_graph()
        self.app = self.graph.compile()

    def run(
        self,
        config: PipelineConfig,
        schemas: list[SchemaOverview],
        sample_contents: dict[str, str],
        reference_lifts: list[Lift],
        reference_runs: list[Run],
    ) -> PipelineResult:
        """Run the agent to extract and validate data.

        Args:
            config: The pipeline configuration.
            schemas: Schema overviews for the data sources.
            sample_contents: Dict of URL -> content.
            reference_lifts: Reference lift data for validation.
            reference_runs: Reference run data for validation.

        Returns:
            PipelineResult with extracted data and metrics.
        """
        # Convert Pydantic models to dicts for state
        ref_lifts = [{"name": lift.name, "id": lift.id} for lift in reference_lifts]
        ref_runs = [{"name": run.name, "id": run.id} for run in reference_runs]

        initial_state: AgentState = {
            "config": config,
            "schemas": schemas,
            "sample_contents": sample_contents,
            "reference_lifts": ref_lifts,
            "reference_runs": ref_runs,
            "extracted_lifts": [],
            "extracted_runs": [],
            "lift_coverage": 0.0,
            "run_coverage": 0.0,
            "attempt": 1,
            "max_attempts": self.max_attempts,
            "min_coverage": self.min_coverage,
            "errors": [],
            "debug_info": [],
            "action": AgentAction.EXTRACT_DATA,
            "is_complete": False,
        }

        # Run the graph
        final_state = self.app.invoke(initial_state)  # type: ignore[arg-type]

        # Build result
        success = final_state["action"] == AgentAction.COMPLETE
        config.lift_coverage = final_state["lift_coverage"]
        config.run_coverage = final_state["run_coverage"]
        config.is_validated = success

        return PipelineResult(
            resort_id=config.resort_id,
            success=success,
            config=config,
            lifts_data=final_state["extracted_lifts"],
            runs_data=final_state["extracted_runs"],
            lift_coverage=final_state["lift_coverage"],
            run_coverage=final_state["run_coverage"],
            errors=final_state["errors"],
            debug_info={
                "attempts": final_state["attempt"],
                "debug_info": [
                    {"selector": d.selector, "error": d.error, "suggestion": d.suggestion}
                    for d in final_state["debug_info"]
                ],
            },
        )


def run_scraping_agent(
    config: PipelineConfig,
    schemas: list[SchemaOverview],
    sample_contents: dict[str, str],
    reference_lifts: list[Lift],
    reference_runs: list[Run],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> PipelineResult:
    """Convenience function to run the scraping agent.

    Args:
        config: The pipeline configuration.
        schemas: Schema overviews for the data sources.
        sample_contents: Dict of URL -> content.
        reference_lifts: Reference lift data for validation.
        reference_runs: Reference run data for validation.
        max_attempts: Maximum refinement attempts.
        min_coverage: Minimum coverage threshold.

    Returns:
        PipelineResult with extracted data and metrics.
    """
    agent = ScrapingAgent(max_attempts=max_attempts, min_coverage=min_coverage)
    return agent.run(config, schemas, sample_contents, reference_lifts, reference_runs)
