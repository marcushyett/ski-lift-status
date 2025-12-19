"""Network traffic capture using XHR Fetcher API.

This module captures all network traffic from a ski resort status page
using a custom XHR Fetcher service that provides full XHR response bodies,
which is critical for discovering API endpoints.

Categorizes requests into types useful for config building:
- XHR/Fetch requests (likely API calls) with full response bodies
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
    cookies: list[dict] = field(default_factory=list)
    console_messages: list[str] = field(default_factory=list)

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
            "cookies": self.cookies,
            "console_messages": self.console_messages,
        }


def _classify_resource_type(
    resource_type: str | None, content_type: str, url: str
) -> ResourceType:
    """Classify resource type from API data and content type."""
    content_type_lower = content_type.lower() if content_type else ""
    url_lower = url.lower()
    resource_type_lower = resource_type.lower() if resource_type else ""

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

    # Check resource type from API
    if resource_type_lower in ("xhr", "fetch"):
        return ResourceType.XHR
    if resource_type_lower == "script":
        return ResourceType.JAVASCRIPT
    if resource_type_lower == "document":
        return ResourceType.HTML
    if resource_type_lower == "stylesheet":
        return ResourceType.CSS
    if resource_type_lower == "image":
        return ResourceType.IMAGE
    if resource_type_lower == "font":
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
        "plausible.io",
        "axept.io",
        "omappapi.com",
        "pixel",
        "/analytics",
        "/tracking",
        "/collect?",
        "/g/collect",
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in tracking_patterns)


def get_xhr_fetcher_config() -> tuple[str | None, str | None]:
    """Get XHR Fetcher API configuration from environment.

    Returns:
        Tuple of (base_url, api_key) or (None, None) if not configured.
    """
    api_key = os.environ.get("XHR_FETCH_KEY")
    # Default to the Fly.io deployment
    base_url = os.environ.get("XHR_FETCH_URL", "https://xhr-fetcher.fly.dev")

    if api_key:
        return base_url, api_key
    return None, None


def _extract_nuxt_data(html: str) -> str | None:
    """Extract and evaluate __NUXT__ data from Nuxt.js pages.

    Nuxt.js stores state in a self-executing function that returns data.
    We need to execute this with Node.js to get the actual JSON.
    """
    import subprocess
    import tempfile
    import os
    import json

    # Find the __NUXT__ script
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    nuxt_script = None
    for script in scripts:
        if 'window.__NUXT__' in script or '__NUXT__' in script:
            nuxt_script = script.strip()
            break

    if not nuxt_script:
        return None

    # Build Node.js script to evaluate and extract the data
    # We need to create a 'window' object since Node.js doesn't have one
    node_script = f'''
// Create window object for browser-style code
const window = {{}};

try {{
    // Evaluate the Nuxt script
    {nuxt_script}

    // Get the result and convert to JSON
    const data = window.__NUXT__;
    if (data) {{
        console.log(JSON.stringify(data));
    }} else {{
        console.log('null');
    }}
}} catch (err) {{
    console.error('Error:', err.message);
    console.log('null');
}}
'''

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(node_script)
            script_path = f.name

        try:
            result = subprocess.run(
                ['node', script_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip() and result.stdout.strip() != 'null':
                # Validate it's valid JSON
                json.loads(result.stdout.strip())
                return result.stdout.strip()
        finally:
            os.unlink(script_path)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    except Exception:
        pass

    return None


def _extract_embedded_json(html: str) -> list[tuple[str, str]]:
    """Extract JSON data embedded in script tags."""
    results = []

    # First try to extract __NUXT__ data (Nuxt.js sites)
    nuxt_data = _extract_nuxt_data(html)
    if nuxt_data:
        results.append(("__NUXT__", nuxt_data))

    # Pattern for script tags with JSON content
    script_patterns = [
        # JSON-LD
        r'<script[^>]*type\s*=\s*["\']application/(?:ld\+)?json["\'][^>]*>(.*?)</script>',
        # Next.js data (different from Nuxt)
        r'<script[^>]*id\s*=\s*["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    ]

    for i, pattern in enumerate(script_patterns):
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            content = match.group(1).strip()
            if content and len(content) > 50:  # Skip tiny snippets
                source = f"embedded_script_{i}_{len(results)}"
                results.append((source, content))

    return results


def _extract_iframes(html: str) -> list[str]:
    """Extract iframe URLs from HTML that might contain data."""
    iframes = []

    # Find all iframe src attributes
    pattern = r'<iframe[^>]*src\s*=\s*["\']([^"\']+)["\']'
    for match in re.finditer(pattern, html, re.IGNORECASE):
        url = match.group(1)
        # Skip Google/analytics iframes
        if not _is_tracking_url(url) and 'googletagmanager' not in url.lower():
            # Unescape HTML entities
            url = url.replace('&amp;', '&')
            # Fix malformed URLs with multiple ? marks
            # e.g., "...station=la-plagne?wmode=transparent" -> "...station=la-plagne&wmode=transparent"
            parts = url.split('?')
            if len(parts) > 2:
                # Keep first ? as query separator, replace others with &
                url = parts[0] + '?' + '&'.join(parts[1:])

            # Remove wmode parameter which causes Skiplan to return incomplete HTML
            # wmode=transparent is a Flash-era parameter that some sites still include
            url = re.sub(r'[&?]wmode=[^&]*', '', url)
            # Clean up any trailing ? or &
            url = url.rstrip('?&')

            iframes.append(url)

    return iframes


async def capture_page_traffic(
    url: str,
    wait_time_ms: int = 10000,
    capture_tracking: bool = False,
    max_body_size: int = 10_000_000,  # 10MB
    wait_selector: str | None = None,
    additional_wait_ms: int = 0,
) -> CapturedTraffic:
    """Capture all network traffic when loading a page using XHR Fetcher API.

    This uses a custom service that captures full XHR response bodies,
    which is critical for discovering API endpoints that return lift status data.

    Args:
        url: The URL to load.
        wait_time_ms: Time to wait for network idle (default 10s).
        capture_tracking: Whether to capture tracking/analytics requests.
        max_body_size: Maximum body size to capture (bytes).
        wait_selector: Optional CSS selector to wait for before capturing.
        additional_wait_ms: Extra wait time after page load.

    Returns:
        CapturedTraffic with all captured resources including XHR response bodies.
    """
    import time

    traffic = CapturedTraffic(page_url=url)
    start_time = time.time()

    base_url, api_key = get_xhr_fetcher_config()
    if not base_url or not api_key:
        traffic.errors.append("No XHR_FETCH_KEY environment variable set")
        return traffic

    try:
        async with httpx.AsyncClient(timeout=180.0, verify=False) as client:
            # Build request payload
            payload = {
                "url": url,
                "waitUntil": "networkidle",
                "timeout": 60000,
                "networkIdleTimeout": wait_time_ms,
            }
            if wait_selector:
                payload["waitForSelector"] = wait_selector
            if additional_wait_ms > 0:
                payload["additionalWaitMs"] = additional_wait_ms

            response = await client.post(
                f"{base_url}/fetch",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                },
            )

            if response.status_code != 200:
                traffic.errors.append(
                    f"XHR Fetcher API error: {response.status_code} - {response.text[:500]}"
                )
                return traffic

            result = response.json()

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                details = result.get("details", "")
                traffic.errors.append(f"XHR Fetcher failed: {error_msg} - {details[:200]}")
                return traffic

            # Parse response
            traffic.final_url = result.get("finalUrl", url)
            traffic.load_time_ms = result.get("loadTimeMs")
            traffic.page_html = result.get("html")
            traffic.cookies = result.get("cookies", [])
            traffic.console_messages = [msg.get("text", "") for msg in result.get("console", [])]

            resources: list[CapturedResource] = []

            # Parse XHR requests with full response bodies
            xhr_requests = result.get("xhrRequests", [])
            for xhr in xhr_requests:
                req_data = xhr.get("request", {})
                resp_data = xhr.get("response", {})

                req_url = req_data.get("url", "")
                if not req_url:
                    continue

                # Skip tracking URLs unless explicitly requested
                if not capture_tracking and _is_tracking_url(req_url):
                    continue

                # Get response body - this is what we couldn't get before!
                body = resp_data.get("body")
                content_type = resp_data.get("contentType", "")
                status_code = resp_data.get("status")

                # Classify resource type
                resource_type = _classify_resource_type(
                    req_data.get("resourceType", "xhr"),
                    content_type,
                    req_url
                )

                # For JSON content, mark as JSON type
                if body and (body.strip().startswith("{") or body.strip().startswith("[")):
                    resource_type = ResourceType.JSON

                resource = CapturedResource(
                    url=req_url,
                    method=req_data.get("method", "GET"),
                    resource_type=resource_type,
                    content_type=content_type,
                    status_code=status_code,
                    request_headers=req_data.get("headers", {}),
                    response_headers=resp_data.get("headers", {}),
                    body=body[:max_body_size] if body and len(body) > max_body_size else body,
                    body_size=len(body) if body else 0,
                )
                resources.append(resource)

            # Extract embedded JSON from HTML
            if traffic.page_html:
                embedded_data = _extract_embedded_json(traffic.page_html)
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

                # Extract iframe URLs for potential follow-up capture
                iframe_urls = _extract_iframes(traffic.page_html)
                for iframe_url in iframe_urls:
                    # Add iframe as a resource so the config builder knows to explore it
                    resource = CapturedResource(
                        url=iframe_url,
                        method="IFRAME",
                        resource_type=ResourceType.HTML,
                        content_type="text/html",
                        status_code=None,  # Not fetched yet
                        request_headers={},
                        response_headers={},
                        body=None,
                        body_size=0,
                    )
                    resources.append(resource)

            traffic.resources = resources
            traffic.load_time_ms = (time.time() - start_time) * 1000

    except httpx.TimeoutException:
        traffic.errors.append("Request timeout while capturing page traffic")
    except httpx.RequestError as e:
        traffic.errors.append(f"Request error: {str(e)}")
    except Exception as e:
        traffic.errors.append(f"Unexpected error: {str(e)}")

    return traffic


async def capture_iframe_traffic(
    iframe_url: str,
    parent_url: str,
    capture_tracking: bool = False,
    max_body_size: int = 10_000_000,
) -> CapturedTraffic:
    """Capture traffic from an iframe URL.

    This is useful for following up on iframes discovered in the main page
    that might contain lift status data (e.g., Lumiplan, Skiplan widgets).

    Args:
        iframe_url: The iframe URL to capture.
        parent_url: The parent page URL (for context).
        capture_tracking: Whether to capture tracking requests.
        max_body_size: Maximum body size to capture.

    Returns:
        CapturedTraffic from the iframe.
    """
    return await capture_page_traffic(
        url=iframe_url,
        capture_tracking=capture_tracking,
        max_body_size=max_body_size,
        # Iframes often need more time to load their content
        wait_time_ms=15000,
        additional_wait_ms=2000,
    )
