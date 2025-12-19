"""Sample object extractor from JSON and HTML content.

This module extracts sample objects that match our criteria (contain
lift names, run names, or status words) to provide examples for
config generation.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from html.parser import HTMLParser

from .status_finder import LIFT_INDICATOR_WORDS, RUN_INDICATOR_WORDS, STATUS_WORDS


@dataclass
class SampleObject:
    """A sample object extracted from content."""

    content: Any  # The actual object/element content
    path: str  # JSON path or CSS selector path
    match_type: str  # "lift_name", "run_name", "status", "mixed"
    matched_terms: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content if isinstance(self.content, (dict, list, str, int, float, bool)) else str(self.content),
            "path": self.path,
            "match_type": self.match_type,
            "matched_terms": self.matched_terms,
            "confidence": self.confidence,
        }


@dataclass
class ExtractionResult:
    """Result of sample extraction."""

    resource_url: str
    content_type: str
    samples: list[SampleObject] = field(default_factory=list)
    total_samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "resource_url": self.resource_url,
            "content_type": self.content_type,
            "samples": [s.to_dict() for s in self.samples],
            "total_samples": self.total_samples,
        }


def _contains_lift_indicator(text: str) -> tuple[bool, list[str]]:
    """Check if text contains lift indicator words."""
    text_lower = text.lower()
    found = []
    for word in LIFT_INDICATOR_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            found.append(word)
    return len(found) > 0, found


def _contains_run_indicator(text: str) -> tuple[bool, list[str]]:
    """Check if text contains run indicator words."""
    text_lower = text.lower()
    found = []
    for word in RUN_INDICATOR_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            found.append(word)
    return len(found) > 0, found


def _contains_status_word(text: str) -> tuple[bool, list[str]]:
    """Check if text contains status words."""
    text_lower = text.lower()
    found = []
    for word in STATUS_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            found.append(word)
    return len(found) > 0, found


def _contains_name(text: str, names: list[str]) -> tuple[bool, list[str]]:
    """Check if text contains any of the given names."""
    text_lower = text.lower()
    found = []
    for name in names:
        if name.lower() in text_lower:
            found.append(name)
    return len(found) > 0, found


def _object_to_text(obj: Any) -> str:
    """Convert object to text for matching."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(str(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_object_to_text(item) for item in obj)
    return str(obj)


def extract_samples_from_json(
    content: str,
    lift_names: list[str] | None = None,
    run_names: list[str] | None = None,
    max_samples: int = 10,
) -> list[SampleObject]:
    """Extract sample objects from JSON content.

    Args:
        content: JSON string content.
        lift_names: List of lift names to search for.
        run_names: List of run names to search for.
        max_samples: Maximum samples to return.

    Returns:
        List of SampleObject with matching objects.
    """
    samples: list[SampleObject] = []
    lift_names = lift_names or []
    run_names = run_names or []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return samples

    def traverse(obj: Any, path: str) -> None:
        if len(samples) >= max_samples:
            return

        text = _object_to_text(obj)

        # Check for matches
        matched_terms = []
        match_types = []

        # Check lift names
        if lift_names:
            has_lift, found = _contains_name(text, lift_names)
            if has_lift:
                matched_terms.extend(found)
                match_types.append("lift_name")

        # Check run names
        if run_names:
            has_run, found = _contains_name(text, run_names)
            if has_run:
                matched_terms.extend(found)
                match_types.append("run_name")

        # Check indicators
        has_lift_ind, found = _contains_lift_indicator(text)
        if has_lift_ind:
            matched_terms.extend(found[:3])
            if "lift_indicator" not in match_types:
                match_types.append("lift_indicator")

        has_run_ind, found = _contains_run_indicator(text)
        if has_run_ind:
            matched_terms.extend(found[:3])
            if "run_indicator" not in match_types:
                match_types.append("run_indicator")

        # Check status words
        has_status, found = _contains_status_word(text)
        if has_status:
            matched_terms.extend(found[:3])
            match_types.append("status")

        # If we found matches, add as sample
        if matched_terms and isinstance(obj, dict):
            match_type = "mixed" if len(match_types) > 1 else match_types[0]
            samples.append(SampleObject(
                content=obj,
                path=path,
                match_type=match_type,
                matched_terms=list(set(matched_terms))[:10],
                confidence=min(1.0, len(matched_terms) * 0.2),
            ))

        # Recurse into children
        if isinstance(obj, dict):
            for key, value in obj.items():
                traverse(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:50]):  # Limit array traversal
                traverse(item, f"{path}[{i}]")

    traverse(data, "$")
    return samples


class HTMLSampleParser(HTMLParser):
    """HTML parser that extracts sample elements."""

    def __init__(
        self,
        lift_names: list[str],
        run_names: list[str],
        max_samples: int = 10,
    ):
        super().__init__()
        self.lift_names = lift_names
        self.run_names = run_names
        self.max_samples = max_samples
        self.samples: list[SampleObject] = []

        self.current_path: list[str] = []
        self.current_element: dict[str, Any] | None = None
        self.current_text = ""

    def _get_css_path(self) -> str:
        """Get current CSS-like path."""
        return " > ".join(self.current_path[-5:])  # Last 5 elements

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening tag."""
        # Build path component
        classes = []
        id_attr = None
        for name, value in attrs:
            if name == "class" and value:
                classes = value.split()[:2]
            elif name == "id" and value:
                id_attr = value

        path_part = tag
        if id_attr:
            path_part += f"#{id_attr}"
        elif classes:
            path_part += f".{'.'.join(classes)}"

        self.current_path.append(path_part)

        # Start new element capture
        self.current_element = {
            "tag": tag,
            "attributes": dict(attrs),
            "text": "",
        }
        self.current_text = ""

    def handle_endtag(self, tag: str) -> None:
        """Handle closing tag."""
        if len(self.samples) >= self.max_samples:
            if self.current_path:
                self.current_path.pop()
            return

        if self.current_element and self.current_element.get("tag") == tag:
            self.current_element["text"] = self.current_text.strip()

            # Check for matches
            text = self.current_text + " " + str(self.current_element.get("attributes", {}))
            matched_terms = []
            match_types = []

            # Check lift names
            has_lift, found = _contains_name(text, self.lift_names)
            if has_lift:
                matched_terms.extend(found)
                match_types.append("lift_name")

            # Check run names
            has_run, found = _contains_name(text, self.run_names)
            if has_run:
                matched_terms.extend(found)
                match_types.append("run_name")

            # Check indicators and status
            has_lift_ind, found = _contains_lift_indicator(text)
            if has_lift_ind:
                matched_terms.extend(found[:3])

            has_status, found = _contains_status_word(text)
            if has_status:
                matched_terms.extend(found[:3])
                match_types.append("status")

            # Add sample if matches found
            if matched_terms:
                match_type = "mixed" if len(match_types) > 1 else (match_types[0] if match_types else "indicator")
                self.samples.append(SampleObject(
                    content=self.current_element,
                    path=self._get_css_path(),
                    match_type=match_type,
                    matched_terms=list(set(matched_terms))[:10],
                    confidence=min(1.0, len(matched_terms) * 0.2),
                ))

        if self.current_path:
            self.current_path.pop()
        self.current_element = None

    def handle_data(self, data: str) -> None:
        """Handle text content."""
        self.current_text += " " + data


def extract_samples_from_html(
    content: str,
    lift_names: list[str] | None = None,
    run_names: list[str] | None = None,
    max_samples: int = 10,
) -> list[SampleObject]:
    """Extract sample elements from HTML content.

    Args:
        content: HTML string content.
        lift_names: List of lift names to search for.
        run_names: List of run names to search for.
        max_samples: Maximum samples to return.

    Returns:
        List of SampleObject with matching elements.
    """
    parser = HTMLSampleParser(
        lift_names=lift_names or [],
        run_names=run_names or [],
        max_samples=max_samples,
    )
    try:
        parser.feed(content)
    except Exception:
        pass

    return parser.samples


def extract_matching_samples(
    content: str,
    content_type: str | None = None,
    lift_names: list[str] | None = None,
    run_names: list[str] | None = None,
    max_samples: int = 10,
) -> ExtractionResult:
    """Extract sample objects from content, auto-detecting type.

    Args:
        content: The content string.
        content_type: Optional content type hint.
        lift_names: List of lift names to search for.
        run_names: List of run names to search for.
        max_samples: Maximum samples to return.

    Returns:
        ExtractionResult with samples.
    """
    result = ExtractionResult(
        resource_url="",
        content_type="unknown",
    )

    content = content.strip()

    # Detect content type
    if content_type and "json" in content_type.lower():
        result.content_type = "json"
        result.samples = extract_samples_from_json(
            content, lift_names, run_names, max_samples
        )
    elif content_type and "html" in content_type.lower():
        result.content_type = "html"
        result.samples = extract_samples_from_html(
            content, lift_names, run_names, max_samples
        )
    elif content.startswith(("{", "[")):
        result.content_type = "json"
        result.samples = extract_samples_from_json(
            content, lift_names, run_names, max_samples
        )
    else:
        result.content_type = "html"
        result.samples = extract_samples_from_html(
            content, lift_names, run_names, max_samples
        )

    result.total_samples = len(result.samples)
    return result
