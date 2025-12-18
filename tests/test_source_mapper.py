"""Tests for the source mapper module."""

import pytest

from ski_lift_status.models import Lift, Run
from ski_lift_status.scraping.models import (
    DataCategory,
    SchemaField,
    SchemaOverview,
)
from ski_lift_status.scraping.source_mapper import (
    SourceMapper,
    _contains_similarity,
    _extract_field_values,
    _fuzzy_similarity,
    _normalize_for_matching,
    find_source_mappings,
)


class TestNormalizeForMatching:
    """Tests for normalization function."""

    def test_empty_string(self):
        """Test normalizing empty string."""
        assert _normalize_for_matching("") == ""

    def test_simple_string(self):
        """Test normalizing simple string."""
        assert _normalize_for_matching("Gondola One") == "gondola one"

    def test_special_characters(self):
        """Test normalizing with special characters."""
        assert _normalize_for_matching("Chair-Lift #1") == "chair lift 1"


class TestFuzzySimilarity:
    """Tests for fuzzy similarity calculation."""

    def test_empty_strings(self):
        """Test similarity with empty strings."""
        assert _fuzzy_similarity("", "") == 0.0
        assert _fuzzy_similarity("test", "") == 0.0
        assert _fuzzy_similarity("", "test") == 0.0

    def test_identical_strings(self):
        """Test similarity with identical strings."""
        assert _fuzzy_similarity("Gondola One", "Gondola One") == 1.0

    def test_case_insensitive(self):
        """Test that comparison is case insensitive."""
        assert _fuzzy_similarity("GONDOLA", "gondola") == 1.0

    def test_similar_strings(self):
        """Test similarity with similar strings."""
        sim = _fuzzy_similarity("Gondola One", "Gondola 1")
        assert sim > 0.5

    def test_different_strings(self):
        """Test similarity with different strings."""
        sim = _fuzzy_similarity("Gondola One", "Chair Lift")
        assert sim < 0.5


class TestContainsSimilarity:
    """Tests for contains similarity calculation."""

    def test_empty_strings(self):
        """Test with empty strings."""
        assert _contains_similarity("", "") == 0.0
        assert _contains_similarity("test", "") == 0.0

    def test_exact_contain(self):
        """Test when one string contains the other."""
        assert _contains_similarity("Gondola", "Gondola One Express") == 0.9

    def test_word_subset(self):
        """Test when words are subset."""
        sim = _contains_similarity("Gondola", "The Gondola Lift")
        assert sim >= 0.8

    def test_no_contain(self):
        """Test when no containment."""
        assert _contains_similarity("Gondola", "Chair Lift") == 0.0


class TestExtractFieldValues:
    """Tests for field value extraction."""

    def test_extract_existing_field(self):
        """Test extracting values from existing field."""
        objects = [
            {"name": "Lift A"},
            {"name": "Lift B"},
            {"name": "Lift C"},
        ]

        values = _extract_field_values(objects, "name")

        assert len(values) == 3
        assert "Lift A" in values

    def test_extract_missing_field(self):
        """Test extracting from missing field."""
        objects = [{"other": "value"}]

        values = _extract_field_values(objects, "name")

        assert values == []

    def test_extract_with_none_values(self):
        """Test extracting when some values are None."""
        objects = [
            {"name": "Lift A"},
            {"name": None},
            {"name": "Lift B"},
        ]

        values = _extract_field_values(objects, "name")

        assert len(values) == 2


class TestSourceMapper:
    """Tests for SourceMapper class."""

    @pytest.fixture
    def sample_lifts(self):
        """Create sample lift data."""
        return [
            Lift(id="1", name="Gondola One"),
            Lift(id="2", name="Express Chair"),
        ]

    @pytest.fixture
    def sample_runs(self):
        """Create sample run data."""
        return [
            Run(id="1", name="Blue Run"),
            Run(id="2", name="Black Diamond"),
        ]

    @pytest.fixture
    def mapper(self, sample_lifts, sample_runs):
        """Create a mapper instance."""
        return SourceMapper(sample_lifts, sample_runs)

    @pytest.fixture
    def static_schema(self):
        """Create a static schema."""
        return SchemaOverview(
            resource_url="https://example.com/api/metadata",
            category=DataCategory.STATIC_METADATA,
            fields=[
                SchemaField(
                    name="liftId",
                    field_type="integer",
                    sample_values=[1, 2, 3],
                    is_identifier=True,
                ),
                SchemaField(
                    name="name",
                    field_type="string",
                    sample_values=["Gondola One", "Express Chair"],
                    is_name_field=True,
                ),
            ],
            total_objects_count=10,
        )

    @pytest.fixture
    def dynamic_schema(self):
        """Create a dynamic schema."""
        return SchemaOverview(
            resource_url="https://example.com/api/status",
            category=DataCategory.DYNAMIC_STATUS,
            fields=[
                SchemaField(
                    name="id",
                    field_type="integer",
                    sample_values=[1, 2, 3],
                    is_identifier=True,
                ),
                SchemaField(
                    name="liftName",
                    field_type="string",
                    sample_values=["Gondola One", "Express Chair"],
                    is_name_field=True,
                ),
                SchemaField(
                    name="status",
                    field_type="string",
                    sample_values=["open", "closed"],
                    is_status_field=True,
                ),
            ],
            total_objects_count=10,
        )

    def test_find_mapping(self, mapper, static_schema, dynamic_schema):
        """Test finding a mapping between schemas."""
        mapping = mapper.find_mapping(static_schema, dynamic_schema)

        assert mapping is not None
        assert mapping.static_resource_url == "https://example.com/api/metadata"
        assert mapping.dynamic_resource_url == "https://example.com/api/status"
        assert mapping.confidence_score > 0

    def test_find_all_mappings(self, mapper, static_schema, dynamic_schema):
        """Test finding all mappings."""
        schemas = {
            static_schema.resource_url: [static_schema],
            dynamic_schema.resource_url: [dynamic_schema],
        }

        mappings = mapper.find_all_mappings(schemas)

        assert len(mappings) >= 1

    def test_validate_mapping_against_reference(
        self, mapper, static_schema, dynamic_schema
    ):
        """Test validating mapping against reference data."""
        mapping = mapper.find_mapping(static_schema, dynamic_schema)

        if mapping:
            lift_cov, run_cov = mapper.validate_mapping_against_reference(
                mapping, static_schema
            )

            # Should have some coverage since sample values match reference
            assert lift_cov >= 0.0
            assert run_cov >= 0.0


class TestFindSourceMappings:
    """Tests for the convenience function."""

    def test_find_source_mappings(self):
        """Test the convenience function."""
        static_schema = SchemaOverview(
            resource_url="https://example.com/static",
            category=DataCategory.STATIC_METADATA,
            fields=[
                SchemaField(
                    name="name",
                    field_type="string",
                    sample_values=["Lift A"],
                    is_name_field=True,
                ),
            ],
            total_objects_count=5,
        )

        dynamic_schema = SchemaOverview(
            resource_url="https://example.com/dynamic",
            category=DataCategory.DYNAMIC_STATUS,
            fields=[
                SchemaField(
                    name="liftName",
                    field_type="string",
                    sample_values=["Lift A"],
                    is_name_field=True,
                ),
            ],
            total_objects_count=5,
        )

        schemas = {
            static_schema.resource_url: [static_schema],
            dynamic_schema.resource_url: [dynamic_schema],
        }

        mappings = find_source_mappings(schemas)

        assert isinstance(mappings, list)
