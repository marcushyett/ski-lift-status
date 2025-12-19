"""Schema extraction from JSON and HTML content.

This module extracts a structural overview/schema from response content
without including all the data - useful for understanding the structure
without overwhelming context windows.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from html.parser import HTMLParser


@dataclass
class SchemaNode:
    """A node in the extracted schema."""

    type: str  # "object", "array", "string", "number", "boolean", "null", "element"
    tag: str | None = None  # HTML tag name
    keys: list[str] = field(default_factory=list)  # Object keys
    attributes: list[str] = field(default_factory=list)  # HTML attributes
    children: list["SchemaNode"] = field(default_factory=list)
    array_length: int | None = None  # For arrays
    sample_value: str | None = None  # Sample for primitives
    css_classes: list[str] = field(default_factory=list)  # CSS classes
    id_attr: str | None = None  # HTML id attribute
    repeat_count: int = 1  # How many times this pattern repeats

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"type": self.type}

        if self.tag:
            result["tag"] = self.tag
        if self.keys:
            result["keys"] = self.keys
        if self.attributes:
            result["attributes"] = self.attributes
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.array_length is not None:
            result["array_length"] = self.array_length
        if self.sample_value is not None:
            result["sample_value"] = self.sample_value
        if self.css_classes:
            result["css_classes"] = self.css_classes
        if self.id_attr:
            result["id"] = self.id_attr
        if self.repeat_count > 1:
            result["repeat_count"] = self.repeat_count

        return result

    def to_compact_string(self, indent: int = 0) -> str:
        """Convert to compact string representation."""
        prefix = "  " * indent
        parts = []

        if self.type == "object":
            parts.append(f"{prefix}{{")
            for key in self.keys[:10]:  # Limit keys shown
                parts.append(f"{prefix}  {key}: ...")
            if len(self.keys) > 10:
                parts.append(f"{prefix}  ... ({len(self.keys) - 10} more keys)")
            parts.append(f"{prefix}}}")
        elif self.type == "array":
            parts.append(f"{prefix}[{self.array_length} items]")
            for child in self.children[:1]:  # Show first array item structure
                parts.append(child.to_compact_string(indent + 1))
        elif self.type == "element":
            attrs = " ".join(self.attributes[:3])
            classes = " ".join(self.css_classes[:3])
            id_str = f"#{self.id_attr}" if self.id_attr else ""
            class_str = f".{'.'.join(self.css_classes[:3])}" if self.css_classes else ""
            repeat_str = f" x{self.repeat_count}" if self.repeat_count > 1 else ""
            parts.append(f"{prefix}<{self.tag}{id_str}{class_str}{repeat_str}>")
            for child in self.children[:5]:
                parts.append(child.to_compact_string(indent + 1))
            if len(self.children) > 5:
                parts.append(f"{prefix}  ... ({len(self.children) - 5} more)")
            parts.append(f"{prefix}</{self.tag}>")
        else:
            sample = self.sample_value[:50] if self.sample_value else ""
            parts.append(f"{prefix}{self.type}: {sample}")

        return "\n".join(parts)


@dataclass
class ExtractedSchema:
    """Extracted schema from content."""

    content_type: str  # "json", "html", "xml"
    root: SchemaNode | None = None
    total_nodes: int = 0
    depth: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content_type": self.content_type,
            "root": self.root.to_dict() if self.root else None,
            "total_nodes": self.total_nodes,
            "depth": self.depth,
            "error": self.error,
        }


def _extract_json_schema_recursive(
    data: Any,
    max_depth: int = 10,
    current_depth: int = 0,
    max_array_items: int = 3,
) -> tuple[SchemaNode, int, int]:
    """Recursively extract schema from JSON data.

    Returns:
        Tuple of (SchemaNode, total_nodes, max_depth_seen)
    """
    if current_depth >= max_depth:
        return SchemaNode(type="...", sample_value="max depth reached"), 1, current_depth

    if data is None:
        return SchemaNode(type="null"), 1, current_depth

    if isinstance(data, bool):
        return SchemaNode(type="boolean", sample_value=str(data)), 1, current_depth

    if isinstance(data, (int, float)):
        return SchemaNode(type="number", sample_value=str(data)[:20]), 1, current_depth

    if isinstance(data, str):
        sample = data[:100] if len(data) > 100 else data
        return SchemaNode(type="string", sample_value=sample), 1, current_depth

    if isinstance(data, list):
        node = SchemaNode(type="array", array_length=len(data))
        total = 1
        max_d = current_depth

        # Process first few items to understand structure
        for item in data[:max_array_items]:
            child, child_total, child_depth = _extract_json_schema_recursive(
                item, max_depth, current_depth + 1, max_array_items
            )
            node.children.append(child)
            total += child_total
            max_d = max(max_d, child_depth)

        return node, total, max_d

    if isinstance(data, dict):
        node = SchemaNode(type="object", keys=list(data.keys()))
        total = 1
        max_d = current_depth

        # Process first few values to understand structure
        for i, (key, value) in enumerate(data.items()):
            if i >= 20:  # Limit keys processed
                break
            child, child_total, child_depth = _extract_json_schema_recursive(
                value, max_depth, current_depth + 1, max_array_items
            )
            child.sample_value = key  # Store key name
            node.children.append(child)
            total += child_total
            max_d = max(max_d, child_depth)

        return node, total, max_d

    return SchemaNode(type="unknown"), 1, current_depth


def extract_json_schema(content: str, max_depth: int = 10) -> ExtractedSchema:
    """Extract schema from JSON content.

    Args:
        content: JSON string content.
        max_depth: Maximum depth to traverse.

    Returns:
        ExtractedSchema with structural overview.
    """
    try:
        data = json.loads(content)
        root, total_nodes, depth = _extract_json_schema_recursive(data, max_depth)
        return ExtractedSchema(
            content_type="json",
            root=root,
            total_nodes=total_nodes,
            depth=depth,
        )
    except json.JSONDecodeError as e:
        return ExtractedSchema(
            content_type="json",
            error=f"JSON parse error: {e}",
        )


class HTMLSchemaParser(HTMLParser):
    """HTML parser that extracts structural schema."""

    def __init__(self, max_depth: int = 15):
        super().__init__()
        self.max_depth = max_depth
        self.root = SchemaNode(type="element", tag="root")
        self.stack: list[SchemaNode] = [self.root]
        self.total_nodes = 0
        self.current_depth = 0
        self.max_depth_seen = 0

        # For deduplication of repeated patterns
        self.seen_patterns: dict[str, SchemaNode] = {}

    def _get_pattern_key(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        """Generate a key for pattern deduplication."""
        classes = []
        for name, value in attrs:
            if name == "class" and value:
                classes.extend(value.split())
        return f"{tag}:{','.join(sorted(classes[:3]))}"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening tag."""
        if self.current_depth >= self.max_depth:
            return

        self.total_nodes += 1
        self.current_depth += 1
        self.max_depth_seen = max(self.max_depth_seen, self.current_depth)

        # Extract useful attributes
        css_classes = []
        id_attr = None
        other_attrs = []

        for name, value in attrs:
            if name == "class" and value:
                css_classes = value.split()[:5]  # Limit classes
            elif name == "id" and value:
                id_attr = value
            elif name in ("href", "src", "data-", "name", "type"):
                other_attrs.append(name)

        # Check for repeated pattern
        pattern_key = self._get_pattern_key(tag, attrs)
        if pattern_key in self.seen_patterns:
            existing = self.seen_patterns[pattern_key]
            existing.repeat_count += 1
            # Still need to push to stack for proper nesting
            self.stack.append(existing)
            return

        node = SchemaNode(
            type="element",
            tag=tag,
            css_classes=css_classes,
            id_attr=id_attr,
            attributes=other_attrs,
        )

        self.seen_patterns[pattern_key] = node

        # Add to parent
        if self.stack:
            parent = self.stack[-1]
            if len(parent.children) < 20:  # Limit children
                parent.children.append(node)

        self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing tag."""
        if self.stack and self.stack[-1].tag == tag:
            self.stack.pop()
            self.current_depth = max(0, self.current_depth - 1)

    def handle_data(self, data: str) -> None:
        """Handle text content."""
        text = data.strip()
        if text and len(text) > 2 and self.stack:
            # Add text node to show there's content
            parent = self.stack[-1]
            if not any(c.type == "text" for c in parent.children):
                parent.children.append(SchemaNode(
                    type="text",
                    sample_value=text[:50],
                ))
                self.total_nodes += 1


def extract_html_schema(content: str, max_depth: int = 15) -> ExtractedSchema:
    """Extract schema from HTML content.

    Args:
        content: HTML string content.
        max_depth: Maximum depth to traverse.

    Returns:
        ExtractedSchema with structural overview.
    """
    try:
        parser = HTMLSchemaParser(max_depth=max_depth)
        parser.feed(content)

        return ExtractedSchema(
            content_type="html",
            root=parser.root,
            total_nodes=parser.total_nodes,
            depth=parser.max_depth_seen,
        )
    except Exception as e:
        return ExtractedSchema(
            content_type="html",
            error=f"HTML parse error: {e}",
        )


def extract_schema_from_content(
    content: str,
    content_type: str | None = None,
) -> ExtractedSchema:
    """Extract schema from content, auto-detecting type.

    Args:
        content: The content string.
        content_type: Optional content type hint.

    Returns:
        ExtractedSchema with structural overview.
    """
    content = content.strip()

    # Auto-detect content type
    if content_type and "json" in content_type.lower():
        return extract_json_schema(content)

    if content_type and "html" in content_type.lower():
        return extract_html_schema(content)

    # Try to detect from content
    if content.startswith(("{", "[")):
        return extract_json_schema(content)

    if content.startswith("<") and ("html" in content[:500].lower() or
                                     "<!doctype" in content[:100].lower()):
        return extract_html_schema(content)

    # Try JSON first
    try:
        json.loads(content)
        return extract_json_schema(content)
    except json.JSONDecodeError:
        pass

    # Fall back to HTML
    if "<" in content and ">" in content:
        return extract_html_schema(content)

    return ExtractedSchema(
        content_type="unknown",
        error="Could not determine content type",
    )
