"""Tests for foreign key detection."""

import pytest
import json
from ski_lift_status.config_pipeline.analysis.foreign_key_detector import (
    ForeignKeyCandidate,
    ForeignKeyResult,
    detect_foreign_keys,
    find_best_foreign_key,
)


class TestDetectForeignKeys:
    """Tests for detect_foreign_keys function."""

    def test_exact_id_match(self):
        """Test detecting exact ID matches between sources."""
        source = json.dumps([
            {"id": "L1", "name": "Gondola"},
            {"id": "L2", "name": "Chair 1"},
            {"id": "L3", "name": "Chair 2"},
        ])

        target = json.dumps([
            {"lift_id": "L1", "status": "open"},
            {"lift_id": "L2", "status": "closed"},
            {"lift_id": "L3", "status": "hold"},
        ])

        result = detect_foreign_keys(source, target)

        assert len(result.candidates) > 0
        assert result.best_candidate is not None
        assert result.best_candidate.coverage_percent == 100.0
        assert result.best_candidate.match_type == "exact"

    def test_name_matching(self):
        """Test detecting name-based matches."""
        source = json.dumps([
            {"name": "Express Gondola"},
            {"name": "Summit Chair"},
            {"name": "Base Quad"},
        ])

        target = json.dumps([
            {"lift_name": "Express Gondola", "is_open": True},
            {"lift_name": "Summit Chair", "is_open": False},
            {"lift_name": "Base Quad", "is_open": True},
        ])

        result = detect_foreign_keys(source, target)

        assert len(result.candidates) > 0
        assert result.best_candidate.coverage_percent == 100.0

    def test_case_insensitive_match(self):
        """Test case-insensitive matching."""
        source = json.dumps([
            {"name": "GONDOLA"},
            {"name": "CHAIR"},
        ])

        target = json.dumps([
            {"lift": "gondola", "status": "open"},
            {"lift": "chair", "status": "closed"},
        ])

        result = detect_foreign_keys(source, target)

        assert len(result.candidates) > 0
        # Should find case-insensitive match

    def test_partial_coverage(self):
        """Test partial coverage detection."""
        source = json.dumps([
            {"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}, {"id": "5"},
        ])

        target = json.dumps([
            {"ref": "1"}, {"ref": "2"},  # Only 2 out of 5 match
        ])

        result = detect_foreign_keys(source, target, min_coverage=10)

        assert len(result.candidates) > 0
        assert result.best_candidate.coverage_percent == 40.0

    def test_no_match(self):
        """Test when no foreign key relationship exists."""
        source = json.dumps([{"id": "A"}, {"id": "B"}])
        target = json.dumps([{"id": "X"}, {"id": "Y"}])

        result = detect_foreign_keys(source, target)

        # Should have no candidates with significant coverage
        high_coverage = [c for c in result.candidates if c.coverage_percent >= 50]
        assert len(high_coverage) == 0

    def test_invalid_json(self):
        """Test handling of invalid JSON."""
        result = detect_foreign_keys("not json", '{"valid": true}')

        assert len(result.candidates) == 0

    def test_nested_fields(self):
        """Test detecting matches in nested fields."""
        source = json.dumps({
            "data": {
                "lifts": [
                    {"info": {"id": "L1"}},
                    {"info": {"id": "L2"}},
                ]
            }
        })

        target = json.dumps({
            "status": [
                {"lift_ref": "L1", "open": True},
                {"lift_ref": "L2", "open": False},
            ]
        })

        result = detect_foreign_keys(source, target)

        # Should find the nested id field matches lift_ref
        assert len(result.candidates) > 0


class TestFindBestForeignKey:
    """Tests for find_best_foreign_key function."""

    def test_preferred_field_id(self):
        """Test preferring 'id' field when specified."""
        source = json.dumps([
            {"id": "1", "name": "Lift 1", "code": "A"},
            {"id": "2", "name": "Lift 2", "code": "B"},
        ])

        target = json.dumps([
            {"id": "1", "status": "open"},
            {"id": "2", "status": "closed"},
        ])

        result = find_best_foreign_key(source, target, preferred_fields=["id"])

        assert result is not None
        assert "id" in result.source_field.lower() or "id" in result.target_field.lower()

    def test_preferred_field_name(self):
        """Test preferring 'name' field when specified."""
        source = json.dumps([
            {"id": "1", "name": "Gondola"},
            {"id": "2", "name": "Chair"},
        ])

        target = json.dumps([
            {"lift_name": "Gondola", "status": "open"},
            {"lift_name": "Chair", "status": "closed"},
        ])

        result = find_best_foreign_key(source, target, preferred_fields=["name"])

        assert result is not None

    def test_returns_none_when_no_match(self):
        """Test returning None when no foreign key found."""
        source = json.dumps([{"x": "a"}])
        target = json.dumps([{"y": "b"}])

        result = find_best_foreign_key(source, target)

        # May return None or low-coverage candidate
        if result:
            assert result.coverage_percent < 50


class TestForeignKeyCandidate:
    """Tests for ForeignKeyCandidate dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        candidate = ForeignKeyCandidate(
            source_field="id",
            target_field="lift_id",
            match_count=10,
            source_cardinality=10,
            target_cardinality=10,
            coverage_percent=100.0,
            match_type="exact",
            sample_matches=[("1", "1"), ("2", "2")],
        )

        data = candidate.to_dict()

        assert data["source_field"] == "id"
        assert data["target_field"] == "lift_id"
        assert data["coverage_percent"] == 100.0
        assert len(data["sample_matches"]) <= 5


class TestForeignKeyResult:
    """Tests for ForeignKeyResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = ForeignKeyResult(
            source_url="https://example.com/lifts",
            target_url="https://example.com/status",
            candidates=[
                ForeignKeyCandidate(
                    source_field="id",
                    target_field="ref",
                    match_count=5,
                    source_cardinality=5,
                    target_cardinality=5,
                    coverage_percent=100.0,
                    match_type="exact",
                ),
            ],
        )
        result.best_candidate = result.candidates[0]

        data = result.to_dict()

        assert data["source_url"] == "https://example.com/lifts"
        assert len(data["candidates"]) == 1
        assert data["best_candidate"] is not None
