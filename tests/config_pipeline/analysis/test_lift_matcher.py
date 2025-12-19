"""Tests for lift name matching."""

import pytest
from ski_lift_status.config_pipeline.analysis.lift_matcher import (
    LiftMatch,
    LiftMatchResult,
    find_lift_names_in_content,
    analyze_resources_for_lifts,
)


class TestFindLiftNamesInContent:
    """Tests for find_lift_names_in_content function."""

    def test_exact_match(self):
        """Test exact name matching."""
        lifts = [
            {"id": "lift1", "name": "Gondola Express"},
            {"id": "lift2", "name": "Chair 7"},
        ]
        content = "The Gondola Express is now open. Chair 7 is closed."

        matches = find_lift_names_in_content(content, lifts)

        assert len(matches) == 2
        assert matches[0].lift_id == "lift1"
        assert matches[0].match_type == "exact"
        assert matches[0].confidence == 1.0

    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        lifts = [{"id": "lift1", "name": "Thunder Chair"}]
        content = "The THUNDER CHAIR is operating today."

        matches = find_lift_names_in_content(content, lifts)

        assert len(matches) == 1
        assert matches[0].match_type == "case_insensitive"
        assert matches[0].confidence == 0.95

    def test_fuzzy_match(self):
        """Test fuzzy matching for slight misspellings."""
        lifts = [{"id": "lift1", "name": "Télésiège Nord"}]
        content = "Le telesiege nord est ouvert."

        matches = find_lift_names_in_content(content, lifts, fuzzy_threshold=70)

        assert len(matches) >= 1
        assert matches[0].match_type in ("fuzzy", "case_insensitive")

    def test_no_match(self):
        """Test when no matches are found."""
        lifts = [{"id": "lift1", "name": "Avalanche Express"}]
        content = "All lifts are closed due to weather."

        matches = find_lift_names_in_content(content, lifts)

        assert len(matches) == 0

    def test_short_names_skipped(self):
        """Test that very short names are handled properly."""
        lifts = [
            {"id": "lift1", "name": "A"},  # Too short
            {"id": "lift2", "name": "Chair A"},
        ]
        content = "A is open. Chair A is running."

        matches = find_lift_names_in_content(content, lifts)

        # Only Chair A should match, not "A" alone (too short)
        assert len(matches) == 1
        assert matches[0].lift_name == "Chair A"

    def test_context_extraction(self):
        """Test that context is extracted correctly."""
        lifts = [{"id": "lift1", "name": "Blue Chair"}]
        content = "Operating status: Blue Chair - OPEN - 9am to 4pm"

        matches = find_lift_names_in_content(content, lifts)

        assert len(matches) == 1
        assert "Blue Chair" in matches[0].context
        assert "OPEN" in matches[0].context or "Operating" in matches[0].context


class TestAnalyzeResourcesForLifts:
    """Tests for analyze_resources_for_lifts function."""

    def test_multiple_resources(self):
        """Test analyzing multiple resources."""
        lifts = [
            {"id": "lift1", "name": "Express Gondola"},
            {"id": "lift2", "name": "Summit Chair"},
            {"id": "lift3", "name": "Base Quad"},
        ]

        resources = [
            {
                "url": "https://example.com/api/lifts",
                "body": '{"lifts": [{"name": "Express Gondola", "status": "open"}]}',
            },
            {
                "url": "https://example.com/status.html",
                "body": "Express Gondola: Open\nSummit Chair: Closed\nBase Quad: Hold",
            },
        ]

        results = analyze_resources_for_lifts(resources, lifts)

        # Should be sorted by coverage
        assert len(results) == 2
        assert results[0].coverage_percent > results[1].coverage_percent
        assert results[0].resource_url == "https://example.com/status.html"

    def test_coverage_calculation(self):
        """Test that coverage is calculated correctly."""
        lifts = [
            {"id": f"lift{i}", "name": f"Lift {i}"}
            for i in range(10)
        ]

        resources = [
            {
                "url": "https://example.com/api/lifts",
                "body": "Lift 1, Lift 2, Lift 3, Lift 4, Lift 5",  # 50% coverage
            },
        ]

        results = analyze_resources_for_lifts(resources, lifts)

        assert len(results) == 1
        assert results[0].coverage_percent == 50.0
        assert results[0].unique_lifts_found == 5
        assert results[0].total_lifts_expected == 10

    def test_empty_resources(self):
        """Test with empty resources list."""
        lifts = [{"id": "lift1", "name": "Test Lift"}]
        resources = []

        results = analyze_resources_for_lifts(resources, lifts)

        assert len(results) == 0

    def test_resources_without_body(self):
        """Test that resources without body are skipped."""
        lifts = [{"id": "lift1", "name": "Test Lift"}]
        resources = [
            {"url": "https://example.com/api", "body": None},
            {"url": "https://example.com/api2", "body": ""},
        ]

        results = analyze_resources_for_lifts(resources, lifts)

        assert len(results) == 0


class TestLiftMatchResult:
    """Tests for LiftMatchResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = LiftMatchResult(
            resource_url="https://example.com/api",
            matches=[
                LiftMatch(
                    lift_id="lift1",
                    lift_name="Test Lift",
                    matched_text="Test Lift",
                    match_type="exact",
                    confidence=1.0,
                    position=10,
                    context="Status: Test Lift - Open",
                ),
            ],
            unique_lifts_found=1,
            total_lifts_expected=5,
            coverage_percent=20.0,
            match_density=0.5,
        )

        data = result.to_dict()

        assert data["resource_url"] == "https://example.com/api"
        assert len(data["matches"]) == 1
        assert data["matches"][0]["lift_id"] == "lift1"
        assert data["coverage_percent"] == 20.0
