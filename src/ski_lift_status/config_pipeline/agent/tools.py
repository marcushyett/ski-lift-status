"""Debug tools for the LangGraph agent.

These tools allow the LLM to debug config issues without loading
full response content into the context window. Each tool returns
minimal, focused information.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup


@dataclass
class DebugTool:
    """A debug tool that can be called by the agent."""

    name: str
    description: str
    parameters: dict[str, Any]


# Tool definitions for LLM
AGENT_TOOLS = [
    DebugTool(
        name="fetch_url_debug",
        description="Fetch a URL and return summary info (status, content type, size, first 500 chars of relevant content)",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    ),
    DebugTool(
        name="analyze_response_structure",
        description="Analyze JSON/HTML structure and return schema summary with field names and types",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to analyze"},
                "content_type": {"type": "string", "enum": ["json", "html"], "description": "Expected content type"},
            },
            "required": ["url"],
        },
    ),
    DebugTool(
        name="test_selector",
        description="Test a selector against a URL and return match count and sample values",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to test against"},
                "selector": {"type": "string", "description": "JSONPath or CSS selector"},
                "selector_type": {"type": "string", "enum": ["json_path", "css_selector"], "description": "Type of selector"},
            },
            "required": ["url", "selector", "selector_type"],
        },
    ),
    DebugTool(
        name="suggest_status_mapping",
        description="Analyze status values in a response and suggest normalized mappings",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL containing status data"},
                "status_selector": {"type": "string", "description": "Selector for status values"},
                "selector_type": {"type": "string", "enum": ["json_path", "css_selector"]},
            },
            "required": ["url", "status_selector", "selector_type"],
        },
    ),
]


async def _fetch_content(url: str) -> tuple[str | None, str | None, dict[str, str]]:
    """Fetch URL content.

    Returns (content, error, response_info).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8",
                },
                follow_redirects=True,
            )

            info = {
                "status_code": str(response.status_code),
                "content_type": response.headers.get("content-type", "unknown"),
                "content_length": str(len(response.text)),
            }

            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}", info

            return response.text, None, info

    except Exception as e:
        return None, str(e), {}


async def fetch_url_debug(url: str) -> dict[str, Any]:
    """Fetch a URL and return debug summary.

    Returns minimal info to help debug issues without overwhelming context.
    """
    content, error, info = await _fetch_content(url)

    if error:
        return {
            "success": False,
            "error": error,
            "info": info,
        }

    # Determine content type
    content_type = info.get("content_type", "")
    is_json = "json" in content_type or (content and content.strip().startswith(("{", "[")))

    # Extract preview
    if is_json:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                preview = f"Object with keys: {list(data.keys())[:10]}"
            elif isinstance(data, list):
                preview = f"Array with {len(data)} items"
                if data and isinstance(data[0], dict):
                    preview += f", first item keys: {list(data[0].keys())[:10]}"
            else:
                preview = str(data)[:500]
        except json.JSONDecodeError:
            preview = content[:500] if content else ""
    else:
        # HTML - extract text preview
        if content:
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            preview = text[:500]
        else:
            preview = ""

    return {
        "success": True,
        "info": info,
        "is_json": is_json,
        "preview": preview,
    }


async def analyze_response_structure(
    url: str,
    content_type: str = "auto",
) -> dict[str, Any]:
    """Analyze response structure and return schema summary."""
    content, error, info = await _fetch_content(url)

    if error:
        return {"success": False, "error": error}

    if not content:
        return {"success": False, "error": "Empty response"}

    # Auto-detect content type
    if content_type == "auto":
        ct = info.get("content_type", "")
        if "json" in ct or content.strip().startswith(("{", "[")):
            content_type = "json"
        else:
            content_type = "html"

    if content_type == "json":
        try:
            data = json.loads(content)
            schema = _extract_json_schema_summary(data)
            return {
                "success": True,
                "content_type": "json",
                "schema": schema,
            }
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON parse error: {e}"}

    else:  # HTML
        schema = _extract_html_schema_summary(content)
        return {
            "success": True,
            "content_type": "html",
            "schema": schema,
        }


def _extract_json_schema_summary(data: Any, max_depth: int = 3, depth: int = 0) -> dict:
    """Extract JSON schema summary."""
    if depth >= max_depth:
        return {"type": "...", "truncated": True}

    if data is None:
        return {"type": "null"}
    if isinstance(data, bool):
        return {"type": "boolean", "example": data}
    if isinstance(data, (int, float)):
        return {"type": "number", "example": data}
    if isinstance(data, str):
        return {"type": "string", "example": data[:50]}

    if isinstance(data, list):
        if not data:
            return {"type": "array", "length": 0}

        # Sample first few items
        sample_schemas = [
            _extract_json_schema_summary(item, max_depth, depth + 1)
            for item in data[:3]
        ]

        return {
            "type": "array",
            "length": len(data),
            "item_schema": sample_schemas[0] if len(set(str(s) for s in sample_schemas)) == 1 else sample_schemas,
        }

    if isinstance(data, dict):
        fields = {}
        for key, value in list(data.items())[:15]:
            fields[key] = _extract_json_schema_summary(value, max_depth, depth + 1)

        if len(data) > 15:
            fields["..."] = f"{len(data) - 15} more fields"

        return {"type": "object", "fields": fields}

    return {"type": "unknown"}


def _extract_html_schema_summary(content: str) -> dict:
    """Extract HTML schema summary focusing on data-containing elements."""
    soup = BeautifulSoup(content, "html.parser")

    # Find elements that might contain lift/run data
    # Look for lists, tables, divs with data classes
    potential_containers = []

    # Tables
    for table in soup.find_all("table")[:5]:
        headers = [th.get_text(strip=True) for th in table.find_all("th")][:10]
        rows = len(table.find_all("tr"))
        potential_containers.append({
            "type": "table",
            "headers": headers,
            "row_count": rows,
            "selector": _build_selector(table),
        })

    # Lists with class names suggesting data
    data_classes = ["lift", "piste", "run", "slope", "status", "list", "item"]
    for ul in soup.find_all(["ul", "ol", "div"])[:10]:
        classes = ul.get("class", [])
        if any(dc in " ".join(classes).lower() for dc in data_classes):
            items = ul.find_all(["li", "div"], recursive=False)[:5]
            potential_containers.append({
                "type": "list",
                "classes": classes[:3],
                "item_count": len(items),
                "selector": _build_selector(ul),
                "sample_text": items[0].get_text(strip=True)[:100] if items else None,
            })

    return {
        "title": soup.title.string if soup.title else None,
        "potential_data_containers": potential_containers[:10],
    }


def _build_selector(element) -> str:
    """Build a CSS selector for an element."""
    parts = [element.name]

    if element.get("id"):
        return f"#{element['id']}"

    classes = element.get("class", [])
    if classes:
        # Use first few stable-looking classes (not random strings)
        stable_classes = [c for c in classes if len(c) < 30 and not re.match(r'^[a-z]{1,3}\d+', c)][:2]
        if stable_classes:
            parts.append("." + ".".join(stable_classes))

    return "".join(parts)


async def test_selector(
    url: str,
    selector: str,
    selector_type: str = "json_path",
) -> dict[str, Any]:
    """Test a selector against content and return matches."""
    content, error, _ = await _fetch_content(url)

    if error:
        return {"success": False, "error": error}

    if not content:
        return {"success": False, "error": "Empty response"}

    if selector_type == "json_path":
        try:
            data = json.loads(content)
            matches = _apply_json_path(data, selector)

            if matches is None:
                return {"success": True, "match_count": 0, "samples": []}

            if isinstance(matches, list):
                return {
                    "success": True,
                    "match_count": len(matches),
                    "samples": [_truncate_value(m) for m in matches[:5]],
                }
            else:
                return {
                    "success": True,
                    "match_count": 1,
                    "samples": [_truncate_value(matches)],
                }

        except json.JSONDecodeError:
            return {"success": False, "error": "Content is not valid JSON"}

    else:  # css_selector
        soup = BeautifulSoup(content, "html.parser")
        try:
            elements = soup.select(selector)
            return {
                "success": True,
                "match_count": len(elements),
                "samples": [
                    {
                        "tag": el.name,
                        "text": el.get_text(strip=True)[:100],
                        "classes": el.get("class", [])[:3],
                    }
                    for el in elements[:5]
                ],
            }
        except Exception as e:
            return {"success": False, "error": f"Selector error: {e}"}


def _apply_json_path(data: Any, path: str) -> Any:
    """Apply a simple JSON path to data."""
    if not path or path == "$":
        return data

    # Remove leading $.
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    parts = path.split(".")
    result = data

    for part in parts:
        if result is None:
            return None

        # Handle array notation
        if "[" in part:
            field, rest = part.split("[", 1)
            idx_str = rest.rstrip("]")

            if field:
                if isinstance(result, dict):
                    result = result.get(field)
                else:
                    return None

            if idx_str == "*" and isinstance(result, list):
                # Continue with remaining path on all items
                remaining = ".".join(parts[parts.index(part) + 1:])
                if remaining:
                    return [_apply_json_path(item, remaining) for item in result]
                return result
            elif idx_str.isdigit():
                idx = int(idx_str)
                if isinstance(result, list) and 0 <= idx < len(result):
                    result = result[idx]
                else:
                    return None
        else:
            if isinstance(result, dict):
                result = result.get(part)
            else:
                return None

    return result


def _truncate_value(value: Any, max_len: int = 200) -> Any:
    """Truncate a value for display."""
    if isinstance(value, str):
        return value[:max_len] + "..." if len(value) > max_len else value
    if isinstance(value, dict):
        return {k: _truncate_value(v, 50) for k, v in list(value.items())[:10]}
    if isinstance(value, list):
        return [_truncate_value(v, 50) for v in value[:5]]
    return value


async def suggest_status_mapping(
    url: str,
    status_selector: str,
    selector_type: str = "json_path",
) -> dict[str, Any]:
    """Analyze status values and suggest mappings."""
    content, error, _ = await _fetch_content(url)

    if error:
        return {"success": False, "error": error}

    # Extract status values
    status_values = []

    if selector_type == "json_path":
        try:
            data = json.loads(content)
            values = _apply_json_path(data, status_selector)
            if isinstance(values, list):
                status_values = [str(v) for v in values if v]
            elif values:
                status_values = [str(values)]
        except json.JSONDecodeError:
            return {"success": False, "error": "Not valid JSON"}
    else:
        soup = BeautifulSoup(content, "html.parser")
        elements = soup.select(status_selector)
        status_values = [el.get_text(strip=True) for el in elements]

    # Count unique values
    from collections import Counter
    value_counts = Counter(status_values)

    # Suggest mappings
    suggestions = {}
    for value, count in value_counts.most_common(20):
        value_lower = value.lower()

        # Try to map to standard values
        if any(w in value_lower for w in ["open", "ouvert", "geöffnet", "aperto"]):
            suggestions[value] = "open"
        elif any(w in value_lower for w in ["closed", "fermé", "geschlossen", "chiuso"]):
            suggestions[value] = "closed"
        elif any(w in value_lower for w in ["hold", "standby", "attente"]):
            suggestions[value] = "hold"
        elif any(w in value_lower for w in ["wind"]):
            suggestions[value] = "wind_hold"
        elif any(w in value_lower for w in ["groomed", "damé", "präpariert"]):
            suggestions[value] = "groomed"
        else:
            suggestions[value] = "unknown"

    return {
        "success": True,
        "unique_values": len(value_counts),
        "value_counts": dict(value_counts.most_common(20)),
        "suggested_mapping": suggestions,
    }
