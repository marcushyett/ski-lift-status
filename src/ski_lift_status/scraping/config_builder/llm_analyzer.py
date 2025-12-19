"""LLM-based traffic analyzer for autonomous config building.

This module uses GPT-4o-mini to analyze captured network traffic and
identify lift/trail status data in ANY format from ANY platform.
No hardcoded patterns - fully AI-driven analysis.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

import structlog
from openai import AsyncOpenAI

from .network_capture import NetworkTraffic

logger = structlog.get_logger()


@dataclass
class IdentifiedEndpoint:
    """An endpoint identified as containing lift/trail status data."""

    url: str
    method: str
    content_type: str
    data_format: str  # "json", "html", "xml", "javascript"
    confidence: float
    reasoning: str

    # Extraction details
    extraction_path: str | None = None  # JSON path, CSS selector, XPath, etc.
    sample_data: dict | None = None  # Sample of extracted data

    # For dynamic extraction
    lift_selector: str | None = None
    trail_selector: str | None = None
    status_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class TrafficAnalysis:
    """Result of LLM analysis of network traffic."""

    success: bool
    endpoints: list[IdentifiedEndpoint]
    primary_endpoint: IdentifiedEndpoint | None
    platform_hint: str | None  # Optional hint like "skiplan-like", "json-api", etc.
    reasoning: str
    extraction_code: str | None = None  # Generated Python code for extraction
    errors: list[str] = field(default_factory=list)


def _get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client with API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return AsyncOpenAI(api_key=api_key)


def _prepare_traffic_summary(traffic: NetworkTraffic, max_requests: int = 50) -> str:
    """Prepare a summary of network traffic for LLM analysis.

    Focuses on requests that are likely to contain status data:
    - JSON/XML/HTML responses
    - Requests to API endpoints
    - Excludes images, fonts, tracking pixels, etc.
    """
    relevant_requests = []

    for req in traffic.requests:
        # Skip non-data content types
        content_type = req.content_type or ""
        if any(skip in content_type for skip in ["image/", "font/", "video/", "audio/"]):
            continue

        # Skip tracking/analytics
        url_lower = req.url.lower()
        if any(skip in url_lower for skip in [
            "google-analytics", "googletagmanager", "facebook.com/tr",
            "doubleclick", "analytics", "tracking", "pixel", ".gif?",
            "fonts.googleapis", "fonts.gstatic"
        ]):
            continue

        # Build request summary
        summary = {
            "url": req.url[:500],  # Truncate long URLs
            "method": req.method,
            "content_type": content_type,
            "status": req.status,
            "response_size": len(req.content) if req.content else 0,
        }

        # Include response body preview for data responses
        if req.content and len(req.content) > 0:
            body = req.content

            # Try to parse and summarize JSON
            if "json" in content_type or body.strip().startswith(("{", "[")):
                try:
                    data = json.loads(body)
                    # Summarize structure
                    if isinstance(data, dict):
                        summary["response_preview"] = {
                            "type": "object",
                            "keys": list(data.keys())[:20],
                            "sample": _truncate_json(data, max_depth=2)
                        }
                    elif isinstance(data, list) and len(data) > 0:
                        summary["response_preview"] = {
                            "type": "array",
                            "length": len(data),
                            "first_item_keys": list(data[0].keys())[:20] if isinstance(data[0], dict) else None,
                            "sample": _truncate_json(data[:3], max_depth=2)
                        }
                except json.JSONDecodeError:
                    pass

            # For HTML, include a snippet
            if "html" in content_type or body.strip().startswith("<"):
                # Look for status-related keywords in HTML
                body_lower = body.lower()
                has_status_keywords = any(kw in body_lower for kw in [
                    "lift", "piste", "slope", "trail", "run", "open", "closed",
                    "status", "remontée", "télé", "ouvert", "fermé"
                ])
                if has_status_keywords:
                    summary["response_preview"] = {
                        "type": "html",
                        "size": len(body),
                        "has_status_keywords": True,
                        "snippet": body[:2000]
                    }

        relevant_requests.append(summary)

        if len(relevant_requests) >= max_requests:
            break

    return json.dumps(relevant_requests, indent=2, default=str)


def _truncate_json(obj: Any, max_depth: int = 2, current_depth: int = 0) -> Any:
    """Truncate a JSON object to a maximum depth for summarization."""
    if current_depth >= max_depth:
        if isinstance(obj, dict):
            return f"{{...{len(obj)} keys...}}"
        elif isinstance(obj, list):
            return f"[...{len(obj)} items...]"
        elif isinstance(obj, str) and len(obj) > 100:
            return obj[:100] + "..."
        return obj

    if isinstance(obj, dict):
        return {k: _truncate_json(v, max_depth, current_depth + 1) for k, v in list(obj.items())[:10]}
    elif isinstance(obj, list):
        return [_truncate_json(item, max_depth, current_depth + 1) for item in obj[:5]]
    elif isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."
    return obj


ANALYSIS_PROMPT = """You are an expert at analyzing network traffic to identify ski resort lift and trail status data.

I've captured network traffic from a ski resort status page. Your task is to:
1. Identify which request(s) contain lift/trail status data
2. Determine the data format and structure
3. Provide extraction details

IMPORTANT: Be completely platform-agnostic. The data could be in ANY format:
- JSON API responses
- HTML with status elements
- XML data
- JavaScript objects embedded in HTML
- Any other format

For each identified endpoint, provide:
- The URL
- Content type and data format
- Confidence level (0-1)
- How to extract lift names and statuses
- How to extract trail names, statuses, and difficulties

Return your analysis as JSON with this structure:
{
    "success": true/false,
    "reasoning": "explanation of your analysis",
    "platform_hint": "optional platform name if recognizable, or descriptive like 'json-api', 'html-table'",
    "endpoints": [
        {
            "url": "...",
            "method": "GET",
            "content_type": "...",
            "data_format": "json|html|xml|javascript",
            "confidence": 0.9,
            "reasoning": "why this endpoint contains status data",
            "extraction_details": {
                "lift_path": "JSON path or CSS selector for lifts",
                "trail_path": "JSON path or CSS selector for trails",
                "name_field": "field/attribute containing name",
                "status_field": "field/attribute containing status",
                "status_mapping": {"open_value": "open", "closed_value": "closed"}
            }
        }
    ],
    "primary_endpoint_index": 0
}

Network traffic data:
"""

EXTRACTION_CODE_PROMPT = """Based on this endpoint analysis, generate Python code to extract lift and trail status.

The code should:
1. Take the response body (string) as input
2. Parse it according to the data format
3. Return a tuple of (lifts, trails) where each is a list of dicts with keys:
   - name: str
   - status: str ("open", "closed", "unknown")
   - type: str (for lifts: lift type, for trails: difficulty)

Endpoint details:
{endpoint_json}

Response body sample:
{response_sample}

Generate a single Python function called `extract_status` that handles this format.
Only return the Python code, no explanations. The code should be robust and handle edge cases.
"""


async def analyze_traffic(traffic: NetworkTraffic) -> TrafficAnalysis:
    """Analyze network traffic using LLM to identify status data endpoints.

    This is the core of the autonomous config builder - it uses AI to
    understand ANY data format without hardcoded patterns.
    """
    log = logger.bind(component="llm_analyzer")

    try:
        client = _get_openai_client()

        # Prepare traffic summary
        traffic_summary = _prepare_traffic_summary(traffic)
        log.info("prepared_traffic_summary", request_count=len(traffic.requests))

        # Call LLM for analysis
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing web traffic to identify ski resort status data. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": ANALYSIS_PROMPT + traffic_summary
                }
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        result_text = response.choices[0].message.content
        if not result_text:
            return TrafficAnalysis(
                success=False,
                endpoints=[],
                primary_endpoint=None,
                platform_hint=None,
                reasoning="Empty response from LLM",
                errors=["LLM returned empty response"]
            )

        result = json.loads(result_text)
        log.info("llm_analysis_complete", success=result.get("success"))

        # Parse endpoints
        endpoints = []
        for ep_data in result.get("endpoints", []):
            extraction = ep_data.get("extraction_details", {})
            endpoints.append(IdentifiedEndpoint(
                url=ep_data.get("url", ""),
                method=ep_data.get("method", "GET"),
                content_type=ep_data.get("content_type", ""),
                data_format=ep_data.get("data_format", "unknown"),
                confidence=ep_data.get("confidence", 0.0),
                reasoning=ep_data.get("reasoning", ""),
                lift_selector=extraction.get("lift_path"),
                trail_selector=extraction.get("trail_path"),
                status_mapping=extraction.get("status_mapping", {})
            ))

        # Get primary endpoint
        primary_idx = result.get("primary_endpoint_index", 0)
        primary = endpoints[primary_idx] if endpoints and primary_idx < len(endpoints) else None

        return TrafficAnalysis(
            success=result.get("success", False),
            endpoints=endpoints,
            primary_endpoint=primary,
            platform_hint=result.get("platform_hint"),
            reasoning=result.get("reasoning", ""),
        )

    except Exception as e:
        log.error("analysis_failed", error=str(e))
        return TrafficAnalysis(
            success=False,
            endpoints=[],
            primary_endpoint=None,
            platform_hint=None,
            reasoning=f"Analysis failed: {e}",
            errors=[str(e)]
        )


async def generate_extraction_code(
    endpoint: IdentifiedEndpoint,
    response_sample: str
) -> str | None:
    """Generate Python extraction code for an identified endpoint.

    This allows the agent to create extractors for completely new
    platforms without any hardcoded logic.
    """
    log = logger.bind(component="llm_analyzer")

    try:
        client = _get_openai_client()

        endpoint_json = json.dumps({
            "url": endpoint.url,
            "content_type": endpoint.content_type,
            "data_format": endpoint.data_format,
            "lift_selector": endpoint.lift_selector,
            "trail_selector": endpoint.trail_selector,
            "status_mapping": endpoint.status_mapping,
        }, indent=2)

        # Truncate response sample
        sample = response_sample[:5000] if len(response_sample) > 5000 else response_sample

        prompt = EXTRACTION_CODE_PROMPT.format(
            endpoint_json=endpoint_json,
            response_sample=sample
        )

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert Python developer. Generate clean, working code."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )

        code = response.choices[0].message.content
        if code:
            # Clean up code block markers if present
            code = code.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

        log.info("extraction_code_generated", code_length=len(code) if code else 0)
        return code

    except Exception as e:
        log.error("code_generation_failed", error=str(e))
        return None


async def test_extraction_code(code: str, response_body: str) -> tuple[list[dict], list[dict]] | None:
    """Test generated extraction code against actual response data.

    Returns (lifts, trails) if successful, None if failed.
    """
    log = logger.bind(component="llm_analyzer")

    try:
        # Create a safe execution environment
        local_vars: dict[str, Any] = {}

        # Add safe imports
        exec_globals = {
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "hasattr": hasattr,
                "getattr": getattr,
            },
            "json": __import__("json"),
            "re": __import__("re"),
        }

        # Try to import BeautifulSoup if available
        try:
            from bs4 import BeautifulSoup
            exec_globals["BeautifulSoup"] = BeautifulSoup
        except ImportError:
            pass

        # Execute the generated code to define the function
        exec(code, exec_globals, local_vars)

        # Get the extract_status function
        extract_fn = local_vars.get("extract_status")
        if not extract_fn:
            log.warning("no_extract_function", msg="Generated code doesn't define extract_status")
            return None

        # Run extraction
        result = extract_fn(response_body)

        if isinstance(result, tuple) and len(result) == 2:
            lifts, trails = result
            log.info(
                "extraction_test_passed",
                lift_count=len(lifts) if lifts else 0,
                trail_count=len(trails) if trails else 0
            )
            return lifts, trails
        else:
            log.warning("invalid_extraction_result", result_type=type(result).__name__)
            return None

    except Exception as e:
        log.error("extraction_test_failed", error=str(e))
        return None
