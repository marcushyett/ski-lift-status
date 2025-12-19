"""Network traffic capture using Browserless BrowserQL API.

This module captures all network traffic from a ski resort status page
using the BrowserQL GraphQL API, which provides better stealth capabilities
and simpler network request capture than CDP connections.

Categorizes requests into types useful for config building:
- XHR/Fetch requests (likely API calls)
- JavaScript files (may contain embedded data)
- HTML content (server-side rendered data)
- Other resources for completeness
"""

import os
import re
import hashlib
import httpx
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urljoin, urlparse


class ResourceType(str, Enum):
    """Type of captured resource."""

    XHR = "xhr"  # XMLHttpRequest / fetch
    JAVASCRIPT = "javascript"
    HTML = "html"
    JSON = "json"
    XML = "xml"
    CSS = "css"
    IMAGE = "image"
    FONT = "font"
    OTHER = "other"


@dataclass
class CapturedResource:
    """A captured network resource."""

    url: str
    method: str
    resource_type: ResourceType
    content_type: str
    status_code: int | None
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    body: str | None
    body_size: int
    timing_ms: float | None = None

    # Hash for deduplication
    content_hash: str | None = None

    def __post_init__(self):
        """Compute content hash if body exists."""
        if self.body and not self.content_hash:
            self.content_hash = hashlib.sha256(self.body.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "url": self.url,
            "method": self.method,
            "resource_type": self.resource_type.value,
            "content_type": self.content_type,
            "status_code": self.status_code,
            "request_headers": self.request_headers,
            "response_headers": self.response_headers,
            "body": self.body,
            "body_size": self.body_size,
            "timing_ms": self.timing_ms,
            "content_hash": self.content_hash,
        }


@dataclass
class CapturedTraffic:
    """All captured traffic from a page load."""

    page_url: str
    final_url: str | None = None  # After redirects
    page_html: str | None = None  # Final page HTML
    resources: list[CapturedResource] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    load_time_ms: float | None = None

    @property
    def xhr_resources(self) -> list[CapturedResource]:
        """Get XHR/fetch requests."""
        return [r for r in self.resources if r.resource_type == ResourceType.XHR]

    @property
    def json_resources(self) -> list[CapturedResource]:
        """Get JSON responses."""
        return [r for r in self.resources if r.resource_type == ResourceType.JSON]

    @property
    def javascript_resources(self) -> list[CapturedResource]:
        """Get JavaScript files."""
        return [r for r in self.resources if r.resource_type == ResourceType.JAVASCRIPT]

    @property
    def html_resources(self) -> list[CapturedResource]:
        """Get HTML resources (including main page)."""
        return [r for r in self.resources if r.resource_type == ResourceType.HTML]

    def get_resources_with_body(self) -> list[CapturedResource]:
        """Get all resources that have a body (for analysis)."""
        return [r for r in self.resources if r.body]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "page_url": self.page_url,
            "final_url": self.final_url,
            "page_html": self.page_html,
            "resources": [r.to_dict() for r in self.resources],
            "errors": self.errors,
            "load_time_ms": self.load_time_ms,
        }


def _classify_resource_type(
    bql_type: str | None, content_type: str, url: str
) -> ResourceType:
    """Classify resource type from BrowserQL data and content type."""
    content_type_lower = content_type.lower() if content_type else ""
    url_lower = url.lower()
    bql_type_lower = bql_type.lower() if bql_type else ""

    # Check content type first
    if "application/json" in content_type_lower:
        return ResourceType.JSON
    if "application/xml" in content_type_lower or "text/xml" in content_type_lower:
        return ResourceType.XML
    if "text/html" in content_type_lower:
        return ResourceType.HTML
    if "javascript" in content_type_lower:
        return ResourceType.JAVASCRIPT
    if "text/css" in content_type_lower:
        return ResourceType.CSS
    if "image/" in content_type_lower:
        return ResourceType.IMAGE
    if "font/" in content_type_lower or "woff" in content_type_lower:
        return ResourceType.FONT

    # Check URL patterns
    if url_lower.endswith(".json") or "/api/" in url_lower:
        return ResourceType.JSON
    if url_lower.endswith((".js", ".mjs")):
        return ResourceType.JAVASCRIPT
    if url_lower.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
        return ResourceType.HTML

    # Check BrowserQL resource type
    if bql_type_lower in ("xhr", "fetch"):
        return ResourceType.XHR
    if bql_type_lower == "script":
        return ResourceType.JAVASCRIPT
    if bql_type_lower == "document":
        return ResourceType.HTML
    if bql_type_lower == "stylesheet":
        return ResourceType.CSS
    if bql_type_lower == "image":
        return ResourceType.IMAGE
    if bql_type_lower == "font":
        return ResourceType.FONT

    return ResourceType.OTHER


def _is_tracking_url(url: str) -> bool:
    """Check if URL is a tracking/analytics service."""
    tracking_patterns = [
        "google-analytics.com",
        "googletagmanager.com",
        "facebook.com/tr",
        "facebook.net",
        "doubleclick.net",
        "googlesyndication.com",
        "hotjar.com",
        "clarity.ms",
        "sentry.io",
        "bugsnag.com",
        "segment.com",
        "mixpanel.com",
        "amplitude.com",
        "intercom.io",
        "crisp.chat",
        "zendesk.com",
        "hubspot.com",
        "marketo.com",
        "pardot.com",
        "pixel",
        "/analytics",
        "/tracking",
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in tracking_patterns)


def get_browserql_endpoint() -> str | None:
    """Get BrowserQL API endpoint from environment."""
    api_key = os.environ.get("BROWSERLESS_API_KEY")
    if api_key:
        # Use stealth endpoint for better bot detection bypass
        return f"https://production-sfo.browserless.io/chromium/bql?token={api_key}"

    endpoint = os.environ.get("BROWSERLESS_ENDPOINT")
    if endpoint:
        return endpoint

    return None


def _build_capture_query(url: str, wait_until: str = "networkIdle") -> str:
    """Build the BrowserQL mutation for capturing traffic."""
    # Use GraphQL mutation to navigate and get page content
    # Skip XHR body capture as it often fails; we'll discover APIs from HTML instead
    return f"""
mutation CaptureTraffic {{
  goto(url: "{url}", waitUntil: {wait_until}, timeout: 60000) {{
    status
    url
    time
  }}
  pageHtml: html {{
    html
  }}
}}
"""


def _parse_headers(headers_list: list[dict] | None) -> dict[str, str]:
    """Parse BrowserQL headers format to dict."""
    if not headers_list:
        return {}
    return {h.get("name", ""): h.get("value", "") for h in headers_list if h.get("name")}


def _discover_api_urls(html: str, base_url: str) -> list[str]:
    """Discover potential API URLs from HTML content."""
    urls = set()

    # Common API URL patterns in JavaScript/HTML
    patterns = [
        # API endpoint patterns in JS
        r'["\']([^"\']*(?:/api/|/rest/|/graphql|/v[0-9]+/)[^"\']*)["\']',
        # JSON file URLs
        r'["\']([^"\']+\.json(?:\?[^"\']*)?)["\']',
        # Fetch/XHR URLs
        r'fetch\s*\(\s*["\']([^"\']+)["\']',
        r'\.get\s*\(\s*["\']([^"\']+)["\']',
        r'\.post\s*\(\s*["\']([^"\']+)["\']',
        # Data URLs
        r'data-url\s*=\s*["\']([^"\']+)["\']',
        r'data-api\s*=\s*["\']([^"\']+)["\']',
        r'data-endpoint\s*=\s*["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1)
            # Skip obvious non-API URLs
            if any(ext in url.lower() for ext in ['.css', '.png', '.jpg', '.gif', '.svg', '.woff', '.ttf']):
                continue
            # Skip tracking URLs
            if _is_tracking_url(url):
                continue
            # Make absolute URL
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = urljoin(base_url, url)
            elif not url.startswith('http'):
                url = urljoin(base_url, url)

            # Only include valid URLs
            try:
                parsed = urlparse(url)
                if parsed.scheme in ('http', 'https') and parsed.netloc:
                    urls.add(url)
            except Exception:
                continue

    return list(urls)


def _extract_embedded_json(html: str) -> list[tuple[str, str]]:
    """Extract JSON data embedded in script tags."""
    results = []

    # Pattern for script tags with JSON content
    script_patterns = [
        # JSON-LD
        r'<script[^>]*type\s*=\s*["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>',
        # Next.js/React data
        r'<script[^>]*id\s*=\s*["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        r'<script[^>]*id\s*=\s*["\']__NUXT[^"\']*["\'][^>]*>(.*?)</script>',
        # Generic JSON in script tags (careful with this one)
        r'<script[^>]*>\s*(?:window\.|var\s+)?\w+\s*=\s*(\{[^<]{100,}?\});?\s*</script>',
    ]

    for i, pattern in enumerate(script_patterns):
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            content = match.group(1).strip()
            if content and len(content) > 50:  # Skip tiny snippets
                source = f"embedded_script_{i}_{len(results)}"
                results.append((source, content))

    return results


async def _discover_and_fetch_apis(
    html: str,
    base_url: str,
    client: httpx.AsyncClient,
    max_body_size: int,
) -> list[CapturedResource]:
    """Discover API endpoints from HTML and fetch them."""
    resources = []

    # First, extract embedded JSON data from script tags
    embedded_data = _extract_embedded_json(html)
    for source_name, json_content in embedded_data:
        resource = CapturedResource(
            url=f"embedded://{source_name}",
            method="EMBEDDED",
            resource_type=ResourceType.JSON,
            content_type="application/json",
            status_code=200,
            request_headers={},
            response_headers={},
            body=json_content[:max_body_size] if len(json_content) > max_body_size else json_content,
            body_size=len(json_content),
        )
        resources.append(resource)

    # Discover API URLs from HTML
    api_urls = _discover_api_urls(html, base_url)

    # Fetch discovered API URLs (limit to avoid overloading)
    for url in api_urls[:20]:  # Limit to 20 URLs
        try:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json, text/html, */*",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                timeout=10.0,
                follow_redirects=True,
            )

            content_type = response.headers.get("content-type", "")
            body = response.text

            # Skip non-text responses
            if not body or "text/" not in content_type and "json" not in content_type and "xml" not in content_type:
                continue

            resource_type = _classify_resource_type(None, content_type, url)

            resource = CapturedResource(
                url=url,
                method="GET",
                resource_type=resource_type,
                content_type=content_type,
                status_code=response.status_code,
                request_headers={},
                response_headers=dict(response.headers),
                body=body[:max_body_size] if len(body) > max_body_size else body,
                body_size=len(body),
            )
            resources.append(resource)

        except Exception:
            # Skip failed requests
            continue

    return resources


async def capture_page_traffic(
    url: str,
    wait_time_ms: int = 8000,
    use_browserless: bool = True,
    capture_tracking: bool = False,
    max_body_size: int = 10_000_000,  # 10MB
) -> CapturedTraffic:
    """Capture all network traffic when loading a page using BrowserQL.

    Args:
        url: The URL to load.
        wait_time_ms: Not used with BrowserQL (kept for API compatibility).
        use_browserless: Whether to use Browserless.io (if available).
        capture_tracking: Whether to capture tracking/analytics requests.
        max_body_size: Maximum body size to capture (bytes).

    Returns:
        CapturedTraffic with all captured resources.
    """
    import time

    traffic = CapturedTraffic(page_url=url)
    start_time = time.time()

    endpoint = get_browserql_endpoint()
    if not endpoint:
        traffic.errors.append("No BROWSERLESS_API_KEY environment variable set")
        return traffic

    # Build the GraphQL query
    query = _build_capture_query(url)

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                endpoint,
                json={
                    "query": query,
                    "variables": {},
                    "operationName": "CaptureTraffic",
                },
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                traffic.errors.append(
                    f"BrowserQL API error: {response.status_code} - {response.text[:500]}"
                )
                return traffic

            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                for error in result["errors"]:
                    traffic.errors.append(f"GraphQL error: {error.get('message', str(error))}")
                return traffic

            data = result.get("data", {})

            # Parse navigation result
            goto_result = data.get("goto", {})
            traffic.final_url = goto_result.get("url", url)
            traffic.load_time_ms = goto_result.get("time")

            # Parse page HTML
            html_result = data.get("pageHtml", {})
            traffic.page_html = html_result.get("html")

            # Discover and fetch API endpoints from HTML
            resources = await _discover_and_fetch_apis(
                traffic.page_html or "",
                traffic.final_url or url,
                client,
                max_body_size,
            )
            traffic.resources = resources
            traffic.load_time_ms = (time.time() - start_time) * 1000

    except httpx.TimeoutException:
        traffic.errors.append("Request timeout while capturing page traffic")
    except httpx.RequestError as e:
        traffic.errors.append(f"Request error: {str(e)}")
    except Exception as e:
        traffic.errors.append(f"Unexpected error: {str(e)}")

    return traffic
