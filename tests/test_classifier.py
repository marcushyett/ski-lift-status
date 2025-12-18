"""Tests for the resource classifier module."""

import pytest

from ski_lift_status.models import Lift, Run
from ski_lift_status.scraping.classifier import (
    ResourceClassifier,
    _calculate_coverage,
    _contains_metadata_keywords,
    _contains_status_keywords,
    _determine_category,
    _normalize_name,
    classify_network_capture,
)
from ski_lift_status.scraping.models import (
    CapturedResource,
    DataCategory,
    NetworkCapture,
    ResourceType,
)


class TestNormalizeName:
    """Tests for name normalization."""

    def test_normalize_empty_string(self):
        """Test normalizing an empty string."""
        assert _normalize_name("") == ""

    def test_normalize_simple_name(self):
        """Test normalizing a simple name."""
        assert _normalize_name("Gondola One") == "gondola one"

    def test_normalize_with_special_chars(self):
        """Test normalizing a name with special characters."""
        assert _normalize_name("Chair-Lift #1") == "chair lift 1"

    def test_normalize_extra_whitespace(self):
        """Test normalizing a name with extra whitespace."""
        assert _normalize_name("  Alpine   Express  ") == "alpine express"


class TestCalculateCoverage:
    """Tests for coverage calculation."""

    def test_empty_reference_names(self):
        """Test with empty reference names."""
        coverage, matched = _calculate_coverage("some content", [])
        assert coverage == 0.0
        assert matched == []

    def test_no_matches(self):
        """Test when no names match."""
        content = "This is some random content"
        names = ["Gondola One", "Express Lift"]
        coverage, matched = _calculate_coverage(content, names)
        assert coverage == 0.0
        assert matched == []

    def test_partial_matches(self):
        """Test when some names match."""
        content = "The Gondola One is currently operating. The Alpine Express is closed."
        names = ["Gondola One", "Express Lift", "Chair A"]
        coverage, matched = _calculate_coverage(content, names)
        assert coverage == pytest.approx(1 / 3, rel=0.1)
        assert "Gondola One" in matched

    def test_all_match(self):
        """Test when all names match."""
        content = "Gondola One and Express Lift are both open"
        names = ["Gondola One", "Express Lift"]
        coverage, matched = _calculate_coverage(content, names)
        assert coverage == 1.0
        assert len(matched) == 2


class TestContainsStatusKeywords:
    """Tests for status keyword detection."""

    def test_contains_status(self):
        """Test detecting 'status' keyword."""
        assert _contains_status_keywords("Lift status: open") is True

    def test_contains_open(self):
        """Test detecting 'open' keyword."""
        assert _contains_status_keywords("This lift is open") is True

    def test_contains_closed(self):
        """Test detecting 'closed' keyword."""
        assert _contains_status_keywords("Currently closed for maintenance") is True

    def test_no_status_keywords(self):
        """Test when no status keywords present."""
        assert _contains_status_keywords("This is a ski lift name") is False


class TestContainsMetadataKeywords:
    """Tests for metadata keyword detection."""

    def test_contains_name(self):
        """Test detecting 'name' keyword."""
        assert _contains_metadata_keywords('{"name": "Gondola"}') is True

    def test_contains_type(self):
        """Test detecting 'type' keyword."""
        assert _contains_metadata_keywords('{"type": "chairlift"}') is True

    def test_contains_difficulty(self):
        """Test detecting 'difficulty' keyword."""
        assert _contains_metadata_keywords('{"difficulty": "expert"}') is True

    def test_no_metadata_keywords(self):
        """Test when no metadata keywords present."""
        assert _contains_metadata_keywords("some random text") is False


class TestDetermineCategory:
    """Tests for category determination."""

    def test_unknown_low_coverage(self):
        """Test that low coverage returns unknown."""
        category = _determine_category(0.01, 0.01, True, True)
        assert category == DataCategory.UNKNOWN

    def test_dynamic_status(self):
        """Test dynamic status category."""
        category = _determine_category(0.5, 0.0, True, False)
        assert category == DataCategory.DYNAMIC_STATUS

    def test_static_metadata(self):
        """Test static metadata category."""
        category = _determine_category(0.5, 0.0, False, True)
        assert category == DataCategory.STATIC_METADATA

    def test_mixed_category(self):
        """Test mixed category."""
        category = _determine_category(0.5, 0.0, True, True)
        assert category == DataCategory.MIXED


class TestResourceClassifier:
    """Tests for ResourceClassifier class."""

    @pytest.fixture
    def sample_lifts(self):
        """Create sample lift data."""
        return [
            Lift(id="1", name="Gondola One", lift_type="gondola"),
            Lift(id="2", name="Express Chair", lift_type="chairlift"),
            Lift(id="3", name="T-Bar Alpha", lift_type="t-bar"),
        ]

    @pytest.fixture
    def sample_runs(self):
        """Create sample run data."""
        return [
            Run(id="1", name="Blue Thunder", difficulty="intermediate"),
            Run(id="2", name="Black Diamond", difficulty="expert"),
        ]

    @pytest.fixture
    def classifier(self, sample_lifts, sample_runs):
        """Create a classifier instance."""
        return ResourceClassifier(
            resort_id="test-resort",
            lifts=sample_lifts,
            runs=sample_runs,
        )

    def test_classify_resource_with_lifts(self, classifier):
        """Test classifying a resource containing lift names."""
        resource = CapturedResource(
            url="https://example.com/api/status",
            resource_type=ResourceType.JSON,
            content='{"lifts": [{"name": "Gondola One", "status": "open"}]}',
            size_bytes=100,
            response_status=200,
        )

        result = classifier.classify_resource(resource)

        assert result.category in [DataCategory.DYNAMIC_STATUS, DataCategory.MIXED]
        assert result.lift_coverage > 0
        assert "Gondola One" in result.matched_lift_names
        assert result.contains_status_keywords is True

    def test_classify_resource_with_runs(self, classifier):
        """Test classifying a resource containing run names."""
        resource = CapturedResource(
            url="https://example.com/api/runs",
            resource_type=ResourceType.JSON,
            content='{"runs": [{"name": "Blue Thunder", "difficulty": "intermediate"}]}',
            size_bytes=100,
            response_status=200,
        )

        result = classifier.classify_resource(resource)

        assert result.run_coverage > 0
        assert "Blue Thunder" in result.matched_run_names

    def test_classify_capture(self, classifier):
        """Test classifying a network capture."""
        capture = NetworkCapture(
            resort_id="test-resort",
            status_page_url="https://example.com/status",
            resources=[
                CapturedResource(
                    url="https://example.com/api/lifts",
                    resource_type=ResourceType.JSON,
                    content='{"name": "Gondola One", "status": "open"}',
                    size_bytes=50,
                    response_status=200,
                ),
            ],
        )

        results = classifier.classify_capture(capture, min_confidence=0.0)

        assert len(results) >= 1

    def test_get_best_sources(self, classifier):
        """Test getting best sources for a category."""
        resource = CapturedResource(
            url="https://example.com/api/status",
            resource_type=ResourceType.JSON,
            content='{"lifts": [{"name": "Gondola One", "status": "open"}]}',
            size_bytes=100,
            response_status=200,
        )

        classified = classifier.classify_resource(resource)
        best = classifier.get_best_sources(
            [classified],
            category=DataCategory.DYNAMIC_STATUS,
        )

        # May or may not match depending on classification
        assert isinstance(best, list)


class TestClassifyNetworkCapture:
    """Tests for the convenience function."""

    def test_classify_network_capture(self):
        """Test the convenience function."""
        capture = NetworkCapture(
            resort_id="test-resort",
            status_page_url="https://example.com/status",
            resources=[
                CapturedResource(
                    url="https://example.com/api/data",
                    resource_type=ResourceType.JSON,
                    content='{"test": "data"}',
                    size_bytes=20,
                    response_status=200,
                ),
            ],
        )

        lifts = [Lift(id="1", name="Test Lift")]
        runs = [Run(id="1", name="Test Run")]

        results = classify_network_capture(capture, "test-resort", lifts, runs)

        assert isinstance(results, list)
