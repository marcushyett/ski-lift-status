"""Tests for the LangGraph agent module."""

import pytest

from ski_lift_status.models import Lift, Run
from ski_lift_status.scraping.agent import (
    AgentAction,
    AgentState,
    ScrapingAgent,
    _calculate_coverage,
    _extract_field,
    _extract_with_jsonpath,
    build_agent_graph,
    extract_data,
    validate_coverage,
)
from ski_lift_status.scraping.models import (
    DataCategory,
    ExtractionConfig,
    ExtractionType,
    PipelineConfig,
    SchemaOverview,
)


class TestExtractWithJsonpath:
    """Tests for JSONPath extraction."""

    def test_simple_path(self):
        """Test extracting with simple path."""
        content = '{"name": "Gondola"}'
        results = _extract_with_jsonpath(content, "$.name")
        assert results == ["Gondola"]

    def test_array_path(self):
        """Test extracting array elements."""
        content = '{"lifts": [{"name": "A"}, {"name": "B"}]}'
        results = _extract_with_jsonpath(content, "$.lifts[*].name")
        assert results == ["A", "B"]

    def test_invalid_json(self):
        """Test with invalid JSON."""
        content = "not json"
        results = _extract_with_jsonpath(content, "$.name")
        assert results == []

    def test_invalid_path(self):
        """Test with invalid path."""
        content = '{"name": "Test"}'
        results = _extract_with_jsonpath(content, "invalid[[[")
        assert results == []


class TestExtractField:
    """Tests for field extraction."""

    def test_extract_json_path(self):
        """Test extraction with JSON path."""
        content = '{"name": "Gondola One"}'
        results = _extract_field(content, "$.name", ExtractionType.JSON_PATH)
        assert results == ["Gondola One"]

    def test_extract_no_selector(self):
        """Test extraction with no selector."""
        content = '{"name": "Test"}'
        results = _extract_field(content, None, ExtractionType.JSON_PATH)
        assert results == []

    def test_extract_regex(self):
        """Test extraction with regex."""
        content = "Status: OPEN, Status: CLOSED"
        results = _extract_field(content, r"Status: (\w+)", ExtractionType.REGEX)
        assert len(results) == 2


class TestCalculateCoverage:
    """Tests for coverage calculation."""

    def test_empty_reference(self):
        """Test with empty reference names."""
        coverage, matched = _calculate_coverage(["Lift A"], [])
        assert coverage == 0.0
        assert matched == []

    def test_full_coverage(self):
        """Test with full coverage."""
        coverage, matched = _calculate_coverage(
            ["Gondola One", "Express Chair"],
            ["Gondola One", "Express Chair"],
        )
        assert coverage == 1.0
        assert len(matched) == 2

    def test_partial_coverage(self):
        """Test with partial coverage."""
        coverage, matched = _calculate_coverage(
            ["Gondola One"],
            ["Gondola One", "Express Chair"],
        )
        assert coverage == 0.5
        assert len(matched) == 1

    def test_case_insensitive(self):
        """Test that matching is case insensitive."""
        coverage, matched = _calculate_coverage(
            ["gondola one"],
            ["Gondola One"],
        )
        assert coverage == 1.0


class TestAgentState:
    """Tests for agent state management."""

    @pytest.fixture
    def sample_config(self):
        """Create a sample pipeline config."""
        return PipelineConfig(
            resort_id="test-resort",
            resort_name="Test Resort",
            status_page_url="https://example.com/status",
            extraction_configs=[
                ExtractionConfig(
                    resource_url="https://example.com/api/lifts",
                    extraction_type=ExtractionType.JSON_PATH,
                    category=DataCategory.DYNAMIC_STATUS,
                    lift_name_selector="$.lifts[*].name",
                    lift_status_selector="$.lifts[*].status",
                ),
            ],
        )

    @pytest.fixture
    def sample_state(self, sample_config) -> AgentState:
        """Create a sample agent state."""
        return {
            "config": sample_config,
            "schemas": [],
            "sample_contents": {
                "https://example.com/api/lifts": '{"lifts": [{"name": "Gondola One", "status": "open"}]}',
            },
            "reference_lifts": [{"name": "Gondola One", "id": "1"}],
            "reference_runs": [{"name": "Blue Run", "id": "1"}],
            "extracted_lifts": [],
            "extracted_runs": [],
            "lift_coverage": 0.0,
            "run_coverage": 0.0,
            "attempt": 1,
            "max_attempts": 3,
            "min_coverage": 0.20,
            "errors": [],
            "debug_info": [],
            "action": AgentAction.EXTRACT_DATA,
            "is_complete": False,
        }

    def test_extract_data_action(self, sample_state):
        """Test the extract_data action."""
        new_state = extract_data(sample_state)

        assert len(new_state["extracted_lifts"]) == 1
        assert new_state["extracted_lifts"][0]["name"] == "Gondola One"
        assert new_state["action"] == AgentAction.VALIDATE_COVERAGE

    def test_validate_coverage_success(self, sample_state):
        """Test validate_coverage when coverage meets threshold."""
        sample_state["extracted_lifts"] = [{"name": "Gondola One"}]
        sample_state["action"] = AgentAction.VALIDATE_COVERAGE

        new_state = validate_coverage(sample_state)

        assert new_state["lift_coverage"] == 1.0
        assert new_state["action"] == AgentAction.COMPLETE

    def test_validate_coverage_failure(self, sample_state):
        """Test validate_coverage when coverage below threshold."""
        sample_state["extracted_lifts"] = []
        sample_state["action"] = AgentAction.VALIDATE_COVERAGE

        new_state = validate_coverage(sample_state)

        assert new_state["lift_coverage"] == 0.0
        assert new_state["action"] == AgentAction.DEBUG_FAILURE


class TestBuildAgentGraph:
    """Tests for graph building."""

    def test_build_graph(self):
        """Test that graph builds successfully."""
        graph = build_agent_graph()
        assert graph is not None

    def test_graph_has_nodes(self):
        """Test that graph has expected nodes."""
        graph = build_agent_graph()
        nodes = graph.nodes
        assert "extract_data" in nodes
        assert "validate_coverage" in nodes
        assert "debug_failure" in nodes
        assert "refine_config" in nodes
        assert "complete" in nodes
        assert "fail" in nodes


class TestScrapingAgent:
    """Tests for ScrapingAgent class."""

    @pytest.fixture
    def agent(self):
        """Create an agent instance."""
        return ScrapingAgent(max_attempts=3, min_coverage=0.20)

    @pytest.fixture
    def sample_config(self):
        """Create a sample pipeline config."""
        return PipelineConfig(
            resort_id="test-resort",
            resort_name="Test Resort",
            status_page_url="https://example.com/status",
            extraction_configs=[
                ExtractionConfig(
                    resource_url="https://example.com/api/lifts",
                    extraction_type=ExtractionType.JSON_PATH,
                    category=DataCategory.DYNAMIC_STATUS,
                    lift_name_selector="$.lifts[*].name",
                    lift_status_selector="$.lifts[*].status",
                ),
            ],
        )

    def test_agent_initialization(self, agent):
        """Test agent initialization."""
        assert agent.max_attempts == 3
        assert agent.min_coverage == 0.20
        assert agent.graph is not None
        assert agent.app is not None

    def test_run_successful_extraction(self, agent, sample_config):
        """Test running agent with successful extraction."""
        sample_contents = {
            "https://example.com/api/lifts": '{"lifts": [{"name": "Gondola One", "status": "open"}]}',
        }
        reference_lifts = [Lift(id="1", name="Gondola One")]
        reference_runs = []

        result = agent.run(
            config=sample_config,
            schemas=[],
            sample_contents=sample_contents,
            reference_lifts=reference_lifts,
            reference_runs=reference_runs,
        )

        assert result.resort_id == "test-resort"
        assert result.lift_coverage == 1.0
        assert result.success is True
        assert len(result.lifts_data) == 1

    def test_run_failed_extraction(self, agent, sample_config):
        """Test running agent with failed extraction."""
        sample_contents = {
            "https://example.com/api/lifts": '{"lifts": []}',
        }
        reference_lifts = [
            Lift(id="1", name="Gondola One"),
            Lift(id="2", name="Chair A"),
            Lift(id="3", name="Chair B"),
            Lift(id="4", name="Chair C"),
            Lift(id="5", name="Chair D"),
        ]
        reference_runs = []

        result = agent.run(
            config=sample_config,
            schemas=[],
            sample_contents=sample_contents,
            reference_lifts=reference_lifts,
            reference_runs=reference_runs,
        )

        assert result.success is False
        assert result.lift_coverage < 0.20
