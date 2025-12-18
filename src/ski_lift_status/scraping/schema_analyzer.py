"""Schema analyzer for extracting structure from captured resources."""

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from .models import (
    ClassifiedResource,
    DataCategory,
    ResourceType,
    SchemaField,
    SchemaOverview,
)


# Field patterns for identifying field types
NAME_PATTERNS = [
    r"name",
    r"title",
    r"label",
    r"designation",
]

STATUS_PATTERNS = [
    r"status",
    r"state",
    r"condition",
    r"open",
    r"closed",
    r"operating",
    r"available",
]

ID_PATTERNS = [
    r"id",
    r"code",
    r"key",
    r"identifier",
    r"ref",
    r"uid",
]


def _get_field_type(value: Any) -> str:
    """Determine the type of a field value."""
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "number"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, dict):
        return "object"
    else:
        return "unknown"


def _is_name_field(field_name: str) -> bool:
    """Check if a field name indicates it contains names."""
    field_lower = field_name.lower()
    return any(re.search(pattern, field_lower) for pattern in NAME_PATTERNS)


def _is_status_field(field_name: str) -> bool:
    """Check if a field name indicates it contains status info."""
    field_lower = field_name.lower()
    return any(re.search(pattern, field_lower) for pattern in STATUS_PATTERNS)


def _is_identifier_field(field_name: str) -> bool:
    """Check if a field name indicates it's an identifier."""
    field_lower = field_name.lower()
    return any(re.search(pattern, field_lower) for pattern in ID_PATTERNS)


def _extract_sample_values(objects: list[dict], field_name: str, max_samples: int = 5) -> list[Any]:
    """Extract sample values for a field from a list of objects."""
    samples = []
    seen = set()

    for obj in objects:
        if field_name in obj:
            value = obj[field_name]
            # Convert to string for deduplication
            value_str = str(value)
            if value_str not in seen and value is not None:
                samples.append(value)
                seen.add(value_str)
                if len(samples) >= max_samples:
                    break

    return samples


def _find_arrays_in_json(data: Any, path: str = "") -> list[tuple[str, list]]:
    """Find all arrays in a JSON structure with their paths."""
    results = []

    if isinstance(data, list) and data:
        # Check if this is an array of objects (useful data)
        if all(isinstance(item, dict) for item in data[:5]):
            results.append((path or "$", data))

    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            results.extend(_find_arrays_in_json(value, new_path))

    return results


def _analyze_json_array(
    objects: list[dict],
    root_path: str,
    category: DataCategory,
) -> SchemaOverview:
    """Analyze an array of JSON objects to extract schema."""
    if not objects:
        return SchemaOverview(
            resource_url="",
            category=category,
            root_path=root_path,
        )

    # Collect all field names
    all_fields: dict[str, set] = {}  # field_name -> set of types

    for obj in objects[:50]:  # Analyze first 50 objects
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key not in all_fields:
                    all_fields[key] = set()
                all_fields[key].add(_get_field_type(value))

    # Build schema fields
    fields = []
    for field_name, types in all_fields.items():
        # Determine primary type
        types_list = list(types)
        primary_type = types_list[0] if len(types_list) == 1 else "mixed"

        field = SchemaField(
            name=field_name,
            field_type=primary_type,
            sample_values=_extract_sample_values(objects, field_name),
            is_identifier=_is_identifier_field(field_name),
            is_status_field=_is_status_field(field_name),
            is_name_field=_is_name_field(field_name),
        )
        fields.append(field)

    # Get sample objects (up to 3)
    sample_objects = objects[:3] if len(objects) >= 3 else objects

    return SchemaOverview(
        resource_url="",
        category=category,
        fields=fields,
        sample_objects=sample_objects,
        total_objects_count=len(objects),
        root_path=root_path,
    )


def _parse_json_content(content: str) -> Any:
    """Try to parse JSON content, handling various formats."""
    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from JavaScript (var data = {...})
    js_patterns = [
        r"var\s+\w+\s*=\s*(\[[\s\S]*?\]);",
        r"var\s+\w+\s*=\s*(\{[\s\S]*?\});",
        r"const\s+\w+\s*=\s*(\[[\s\S]*?\]);",
        r"const\s+\w+\s*=\s*(\{[\s\S]*?\});",
        r"let\s+\w+\s*=\s*(\[[\s\S]*?\]);",
        r"let\s+\w+\s*=\s*(\{[\s\S]*?\});",
    ]

    for pattern in js_patterns:
        match = re.search(pattern, content)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None


def analyze_json_resource(
    resource: ClassifiedResource,
) -> list[SchemaOverview]:
    """Analyze a JSON resource to extract schema overviews.

    Args:
        resource: The classified resource to analyze.

    Returns:
        List of SchemaOverview objects for each array found.
    """
    content = resource.resource.content
    data = _parse_json_content(content)

    if data is None:
        return []

    # Find all arrays in the JSON
    arrays = _find_arrays_in_json(data)

    if not arrays:
        return []

    overviews = []
    for path, arr in arrays:
        if len(arr) == 0:
            continue

        overview = _analyze_json_array(arr, path, resource.category)
        overview.resource_url = resource.resource.url
        overviews.append(overview)

    return overviews


def _extract_table_data(html_content: str) -> list[dict[str, Any]]:
    """Extract structured data from HTML tables."""
    soup = BeautifulSoup(html_content, "html.parser")
    tables_data = []

    for table in soup.find_all("table"):
        # Get headers
        headers = []
        header_row = table.find("thead")
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

        if not headers:
            # Try first row as headers
            first_row = table.find("tr")
            if first_row:
                headers = [th.get_text(strip=True) for th in first_row.find_all(["th", "td"])]

        if not headers:
            continue

        # Get data rows
        rows = []
        for tr in table.find_all("tr")[1:]:  # Skip header row
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) == len(headers):
                row_dict = dict(zip(headers, cells))
                rows.append(row_dict)

        if rows:
            tables_data.extend(rows)

    return tables_data


def _extract_list_data(html_content: str) -> list[dict[str, Any]]:
    """Extract structured data from HTML lists with specific patterns."""
    soup = BeautifulSoup(html_content, "html.parser")
    items = []

    # Look for common ski lift/run patterns
    patterns = [
        {"container": "div", "class_": re.compile(r"lift|run|trail|status", re.I)},
        {"container": "li", "class_": re.compile(r"lift|run|trail|status", re.I)},
        {"container": "article", "class_": re.compile(r"lift|run|trail", re.I)},
    ]

    for pattern in patterns:
        container = pattern["container"]
        class_pattern = pattern.get("class_")
        elements = soup.find_all(container, class_=class_pattern)  # type: ignore[call-overload]
        for elem in elements:
            item = {}

            # Extract text content
            text = elem.get_text(strip=True)
            if text:
                item["text"] = text

            # Extract data attributes
            for attr, value in elem.attrs.items():
                if attr.startswith("data-"):
                    item[attr] = value

            # Look for name/status elements within
            name_elem = elem.find(class_=re.compile(r"name|title", re.I))
            if name_elem:
                item["name"] = name_elem.get_text(strip=True)

            status_elem = elem.find(class_=re.compile(r"status|state", re.I))
            if status_elem:
                item["status"] = status_elem.get_text(strip=True)

            if item and len(item) > 1:  # More than just text
                items.append(item)

    return items


def analyze_html_resource(
    resource: ClassifiedResource,
) -> list[SchemaOverview]:
    """Analyze an HTML resource to extract schema overviews.

    Args:
        resource: The classified resource to analyze.

    Returns:
        List of SchemaOverview objects.
    """
    content = resource.resource.content
    overviews = []

    # Try to extract table data
    table_data = _extract_table_data(content)
    if table_data:
        overview = _analyze_json_array(table_data, "table", resource.category)
        overview.resource_url = resource.resource.url
        overviews.append(overview)

    # Try to extract list data
    list_data = _extract_list_data(content)
    if list_data:
        overview = _analyze_json_array(list_data, "list", resource.category)
        overview.resource_url = resource.resource.url
        overviews.append(overview)

    return overviews


class SchemaAnalyzer:
    """Analyzes classified resources to extract schema information."""

    def analyze_resource(
        self,
        resource: ClassifiedResource,
    ) -> list[SchemaOverview]:
        """Analyze a classified resource to extract schemas.

        Args:
            resource: The classified resource to analyze.

        Returns:
            List of SchemaOverview objects.
        """
        resource_type = resource.resource.resource_type
        content_type = resource.resource.content_type or ""

        if resource_type == ResourceType.JSON or "json" in content_type.lower():
            return analyze_json_resource(resource)
        elif resource_type == ResourceType.HTML or "html" in content_type.lower():
            return analyze_html_resource(resource)
        elif resource_type == ResourceType.JAVASCRIPT or "javascript" in content_type.lower():
            # JavaScript might contain embedded JSON
            return analyze_json_resource(resource)
        else:
            return []

    def analyze_all(
        self,
        resources: list[ClassifiedResource],
    ) -> dict[str, list[SchemaOverview]]:
        """Analyze all classified resources.

        Args:
            resources: List of classified resources.

        Returns:
            Dict mapping resource URLs to their schema overviews.
        """
        results = {}

        for resource in resources:
            overviews = self.analyze_resource(resource)
            if overviews:
                results[resource.resource.url] = overviews

        return results

    def get_best_schemas(
        self,
        all_schemas: dict[str, list[SchemaOverview]],
        min_objects: int = 3,
    ) -> list[SchemaOverview]:
        """Get the best schemas based on object count and field richness.

        Args:
            all_schemas: Dict of resource URLs to schema overviews.
            min_objects: Minimum number of objects required.

        Returns:
            Sorted list of best schema overviews.
        """
        all_overviews = []
        for overviews in all_schemas.values():
            all_overviews.extend(overviews)

        # Filter by minimum objects
        filtered = [o for o in all_overviews if o.total_objects_count >= min_objects]

        # Score by: number of objects * number of relevant fields
        def score(overview: SchemaOverview) -> float:
            field_score = sum(
                2 if f.is_name_field or f.is_status_field else 1
                for f in overview.fields
            )
            return overview.total_objects_count * field_score

        return sorted(filtered, key=score, reverse=True)


def analyze_classified_resources(
    resources: list[ClassifiedResource],
) -> dict[str, list[SchemaOverview]]:
    """Convenience function to analyze classified resources.

    Args:
        resources: List of classified resources.

    Returns:
        Dict mapping resource URLs to their schema overviews.
    """
    analyzer = SchemaAnalyzer()
    return analyzer.analyze_all(resources)
