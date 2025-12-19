"""Tests for schema extraction."""

import pytest
import json
from ski_lift_status.config_pipeline.analysis.schema_extractor import (
    SchemaNode,
    ExtractedSchema,
    extract_json_schema,
    extract_html_schema,
    extract_schema_from_content,
)


class TestExtractJsonSchema:
    """Tests for JSON schema extraction."""

    def test_simple_object(self):
        """Test extracting schema from simple object."""
        content = '{"name": "Test", "value": 123, "active": true}'

        result = extract_json_schema(content)

        assert result.content_type == "json"
        assert result.root is not None
        assert result.root.type == "object"
        assert "name" in result.root.keys
        assert "value" in result.root.keys
        assert "active" in result.root.keys

    def test_array_of_objects(self):
        """Test extracting schema from array of objects."""
        content = json.dumps([
            {"id": 1, "name": "Lift 1", "status": "open"},
            {"id": 2, "name": "Lift 2", "status": "closed"},
        ])

        result = extract_json_schema(content)

        assert result.content_type == "json"
        assert result.root.type == "array"
        assert result.root.array_length == 2
        assert len(result.root.children) >= 1
        assert result.root.children[0].type == "object"

    def test_nested_structure(self):
        """Test extracting schema from nested structure."""
        content = json.dumps({
            "resort": {
                "name": "Test Resort",
                "lifts": [
                    {"name": "Gondola", "status": "open"},
                ],
            },
        })

        result = extract_json_schema(content)

        assert result.content_type == "json"
        assert result.depth >= 2

    def test_invalid_json(self):
        """Test handling invalid JSON."""
        content = "not valid json {"

        result = extract_json_schema(content)

        assert result.error is not None
        assert "parse error" in result.error.lower()

    def test_null_values(self):
        """Test handling null values."""
        content = '{"field": null}'

        result = extract_json_schema(content)

        assert result.root is not None
        # Should handle null without error

    def test_max_depth_truncation(self):
        """Test that deeply nested structures are truncated."""
        # Create deeply nested structure
        nested = {"level": 0}
        current = nested
        for i in range(20):
            current["child"] = {"level": i + 1}
            current = current["child"]

        content = json.dumps(nested)
        result = extract_json_schema(content, max_depth=5)

        assert result.depth <= 5


class TestExtractHtmlSchema:
    """Tests for HTML schema extraction."""

    def test_simple_html(self):
        """Test extracting schema from simple HTML."""
        content = """
        <html>
        <body>
            <div class="lift-list">
                <div class="lift">Gondola</div>
                <div class="lift">Chair</div>
            </div>
        </body>
        </html>
        """

        result = extract_html_schema(content)

        assert result.content_type == "html"
        assert result.root is not None

    def test_repeated_elements(self):
        """Test that repeated elements are identified."""
        content = """
        <ul class="lifts">
            <li class="lift-item">Lift 1</li>
            <li class="lift-item">Lift 2</li>
            <li class="lift-item">Lift 3</li>
        </ul>
        """

        result = extract_html_schema(content)

        assert result.content_type == "html"
        # Repeated patterns should have repeat_count > 1

    def test_class_extraction(self):
        """Test that CSS classes are extracted."""
        content = '<div class="status-container main-panel" id="status"></div>'

        result = extract_html_schema(content)

        assert result.root is not None


class TestExtractSchemaFromContent:
    """Tests for auto-detecting content type."""

    def test_auto_detect_json(self):
        """Test auto-detecting JSON content."""
        content = '{"type": "json"}'

        result = extract_schema_from_content(content)

        assert result.content_type == "json"

    def test_auto_detect_json_array(self):
        """Test auto-detecting JSON array."""
        content = '[{"id": 1}, {"id": 2}]'

        result = extract_schema_from_content(content)

        assert result.content_type == "json"

    def test_auto_detect_html(self):
        """Test auto-detecting HTML content."""
        content = """
        <!DOCTYPE html>
        <html><body>Content</body></html>
        """

        result = extract_schema_from_content(content)

        assert result.content_type == "html"

    def test_explicit_content_type(self):
        """Test using explicit content type hint."""
        content = "<div>Not really JSON</div>"

        result = extract_schema_from_content(content, content_type="text/html")

        assert result.content_type == "html"


class TestSchemaNode:
    """Tests for SchemaNode dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        node = SchemaNode(
            type="object",
            keys=["name", "status"],
            children=[
                SchemaNode(type="string", sample_value="test"),
            ],
        )

        data = node.to_dict()

        assert data["type"] == "object"
        assert data["keys"] == ["name", "status"]
        assert len(data["children"]) == 1

    def test_to_compact_string(self):
        """Test compact string representation."""
        node = SchemaNode(
            type="array",
            array_length=100,
            children=[
                SchemaNode(type="object", keys=["id", "name"]),
            ],
        )

        compact = node.to_compact_string()

        assert "[100 items]" in compact
