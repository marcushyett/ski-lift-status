"""Tests for the schema analyzer module."""

import json

import pytest

from ski_lift_status.scraping.models import (
    CapturedResource,
    ClassifiedResource,
    DataCategory,
    ResourceType,
)
from ski_lift_status.scraping.schema_analyzer import (
    SchemaAnalyzer,
    _extract_sample_values,
    _find_arrays_in_json,
    _get_field_type,
    _is_identifier_field,
    _is_name_field,
    _is_status_field,
    _parse_json_content,
    analyze_classified_resources,
    analyze_json_resource,
)


class TestGetFieldType:
    """Tests for field type detection."""

    def test_null_type(self):
        """Test detecting null type."""
        assert _get_field_type(None) == "null"

    def test_boolean_type(self):
        """Test detecting boolean type."""
        assert _get_field_type(True) == "boolean"
        assert _get_field_type(False) == "boolean"

    def test_integer_type(self):
        """Test detecting integer type."""
        assert _get_field_type(42) == "integer"

    def test_number_type(self):
        """Test detecting number type."""
        assert _get_field_type(3.14) == "number"

    def test_string_type(self):
        """Test detecting string type."""
        assert _get_field_type("hello") == "string"

    def test_array_type(self):
        """Test detecting array type."""
        assert _get_field_type([1, 2, 3]) == "array"

    def test_object_type(self):
        """Test detecting object type."""
        assert _get_field_type({"key": "value"}) == "object"


class TestFieldPatternDetection:
    """Tests for field pattern detection."""

    def test_is_name_field(self):
        """Test detecting name fields."""
        assert _is_name_field("name") is True
        assert _is_name_field("liftName") is True
        assert _is_name_field("title") is True
        assert _is_name_field("label") is True
        assert _is_name_field("status") is False

    def test_is_status_field(self):
        """Test detecting status fields."""
        assert _is_status_field("status") is True
        assert _is_status_field("liftStatus") is True
        assert _is_status_field("isOpen") is True
        assert _is_status_field("condition") is True
        assert _is_status_field("name") is False

    def test_is_identifier_field(self):
        """Test detecting identifier fields."""
        assert _is_identifier_field("id") is True
        assert _is_identifier_field("liftId") is True
        assert _is_identifier_field("code") is True
        assert _is_identifier_field("key") is True
        assert _is_identifier_field("name") is False


class TestExtractSampleValues:
    """Tests for sample value extraction."""

    def test_extract_from_objects(self):
        """Test extracting sample values from objects."""
        objects = [
            {"name": "Lift A", "status": "open"},
            {"name": "Lift B", "status": "closed"},
            {"name": "Lift C", "status": "open"},
        ]

        samples = _extract_sample_values(objects, "name")

        assert len(samples) == 3
        assert "Lift A" in samples
        assert "Lift B" in samples
        assert "Lift C" in samples

    def test_extract_with_max_samples(self):
        """Test extracting with max samples limit."""
        objects = [{"value": i} for i in range(10)]

        samples = _extract_sample_values(objects, "value", max_samples=3)

        assert len(samples) == 3

    def test_extract_deduplicate(self):
        """Test that sample values are deduplicated."""
        objects = [
            {"status": "open"},
            {"status": "open"},
            {"status": "closed"},
        ]

        samples = _extract_sample_values(objects, "status")

        assert len(samples) == 2

    def test_extract_missing_field(self):
        """Test extracting when field doesn't exist."""
        objects = [{"name": "Test"}]

        samples = _extract_sample_values(objects, "missing_field")

        assert samples == []


class TestFindArraysInJson:
    """Tests for finding arrays in JSON."""

    def test_top_level_array(self):
        """Test finding top-level array."""
        data = [{"id": 1}, {"id": 2}]

        arrays = _find_arrays_in_json(data)

        assert len(arrays) == 1
        assert arrays[0][0] == "$"

    def test_nested_array(self):
        """Test finding nested array."""
        data = {"lifts": [{"id": 1}, {"id": 2}]}

        arrays = _find_arrays_in_json(data)

        assert len(arrays) == 1
        assert arrays[0][0] == "lifts"

    def test_multiple_arrays(self):
        """Test finding multiple arrays."""
        data = {
            "lifts": [{"id": 1}],
            "runs": [{"id": 2}],
        }

        arrays = _find_arrays_in_json(data)

        assert len(arrays) == 2

    def test_empty_array_ignored(self):
        """Test that empty arrays are ignored."""
        data = {"empty": []}

        arrays = _find_arrays_in_json(data)

        assert len(arrays) == 0


class TestParseJsonContent:
    """Tests for JSON content parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON."""
        content = '{"key": "value"}'
        result = _parse_json_content(content)
        assert result == {"key": "value"}

    def test_parse_json_array(self):
        """Test parsing JSON array."""
        content = '[1, 2, 3]'
        result = _parse_json_content(content)
        assert result == [1, 2, 3]

    def test_parse_javascript_var(self):
        """Test parsing JavaScript variable assignment."""
        content = 'var data = {"key": "value"};'
        result = _parse_json_content(content)
        assert result == {"key": "value"}

    def test_parse_javascript_const(self):
        """Test parsing JavaScript const assignment."""
        content = 'const lifts = [{"name": "Lift A"}];'
        result = _parse_json_content(content)
        assert result == [{"name": "Lift A"}]

    def test_parse_invalid_returns_none(self):
        """Test that invalid content returns None."""
        content = "not json at all"
        result = _parse_json_content(content)
        assert result is None


class TestAnalyzeJsonResource:
    """Tests for JSON resource analysis."""

    @pytest.fixture
    def sample_json_resource(self):
        """Create a sample JSON resource."""
        content = json.dumps({
            "lifts": [
                {"id": 1, "name": "Gondola One", "status": "open"},
                {"id": 2, "name": "Chair A", "status": "closed"},
                {"id": 3, "name": "T-Bar", "status": "open"},
            ]
        })

        resource = CapturedResource(
            url="https://example.com/api/lifts",
            resource_type=ResourceType.JSON,
            content_type="application/json",
            content=content,
            size_bytes=len(content),
            response_status=200,
        )

        return ClassifiedResource(
            resource=resource,
            category=DataCategory.DYNAMIC_STATUS,
        )

    def test_analyze_json_resource(self, sample_json_resource):
        """Test analyzing a JSON resource."""
        overviews = analyze_json_resource(sample_json_resource)

        assert len(overviews) == 1
        overview = overviews[0]

        assert overview.resource_url == "https://example.com/api/lifts"
        assert overview.category == DataCategory.DYNAMIC_STATUS
        assert overview.total_objects_count == 3
        assert overview.root_path == "lifts"

        # Check fields
        field_names = [f.name for f in overview.fields]
        assert "id" in field_names
        assert "name" in field_names
        assert "status" in field_names

        # Check sample objects
        assert len(overview.sample_objects) == 3


class TestSchemaAnalyzer:
    """Tests for SchemaAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create an analyzer instance."""
        return SchemaAnalyzer()

    def test_analyze_all(self, analyzer):
        """Test analyzing multiple resources."""
        content = json.dumps([{"name": "Lift", "status": "open"}])

        resource = CapturedResource(
            url="https://example.com/api/lifts",
            resource_type=ResourceType.JSON,
            content_type="application/json",
            content=content,
            size_bytes=len(content),
            response_status=200,
        )

        classified = ClassifiedResource(
            resource=resource,
            category=DataCategory.DYNAMIC_STATUS,
        )

        results = analyzer.analyze_all([classified])

        assert "https://example.com/api/lifts" in results

    def test_get_best_schemas(self, analyzer):
        """Test getting best schemas."""
        content = json.dumps([{"name": f"Lift {i}", "status": "open"} for i in range(10)])

        resource = CapturedResource(
            url="https://example.com/api/lifts",
            resource_type=ResourceType.JSON,
            content_type="application/json",
            content=content,
            size_bytes=len(content),
            response_status=200,
        )

        classified = ClassifiedResource(
            resource=resource,
            category=DataCategory.DYNAMIC_STATUS,
        )

        all_schemas = analyzer.analyze_all([classified])
        best = analyzer.get_best_schemas(all_schemas, min_objects=5)

        assert len(best) == 1
        assert best[0].total_objects_count == 10


class TestAnalyzeClassifiedResources:
    """Tests for the convenience function."""

    def test_analyze_classified_resources(self):
        """Test the convenience function."""
        content = json.dumps([{"name": "Test"}])

        resource = CapturedResource(
            url="https://example.com/data",
            resource_type=ResourceType.JSON,
            content=content,
            size_bytes=len(content),
            response_status=200,
        )

        classified = ClassifiedResource(
            resource=resource,
            category=DataCategory.STATIC_METADATA,
        )

        results = analyze_classified_resources([classified])

        assert isinstance(results, dict)
        assert "https://example.com/data" in results
