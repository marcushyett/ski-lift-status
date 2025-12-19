"""Network traffic capture using Playwright with Browserless.

This module captures all network traffic from a ski resort status page,
categorizing requests into types useful for config building:
- XHR/Fetch requests (likely API calls)
- JavaScript files (may contain embedded data)
- HTML content (server-side rendered data)
- Other resources for completeness
"""

import os
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from playwright.async_api import async_playwright, Response, Request


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
    final_url: str | None  # After redirects
    page_html: str | None  # Final page HTML
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
    playwright_type: str, content_type: str, url: str
) -> ResourceType:
    """Classify resource type from Playwright data and content type."""
    content_type_lower = content_type.lower() if content_type else ""
    url_lower = url.lower()

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

    # Check Playwright resource type
    if playwright_type in ("xhr", "fetch"):
        return ResourceType.XHR
    if playwright_type == "script":
        return ResourceType.JAVASCRIPT
    if playwright_type == "document":
        return ResourceType.HTML
    if playwright_type == "stylesheet":
        return ResourceType.CSS
    if playwright_type == "image":
        return ResourceType.IMAGE
    if playwright_type == "font":
        return ResourceType.FONT

    return ResourceType.OTHER


def _should_capture_body(resource_type: ResourceType, content_type: str) -> bool:
    """Determine if we should capture the body for this resource."""
    # Always capture these types
    if resource_type in (
        ResourceType.XHR,
        ResourceType.JSON,
        ResourceType.XML,
        ResourceType.HTML,
        ResourceType.JAVASCRIPT,
    ):
        return True

    # Skip binary content
    content_type_lower = content_type.lower() if content_type else ""
    if any(
        skip in content_type_lower
        for skip in ["image/", "font/", "video/", "audio/", "octet-stream"]
    ):
        return False

    return False


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


def get_browserless_endpoint() -> str | None:
    """Get Browserless WebSocket endpoint from environment."""
    api_key = os.environ.get("BROWSERLESS_API_KEY")
    if api_key:
        return f"wss://chrome.browserless.io?token={api_key}"

    endpoint = os.environ.get("BROWSERLESS_ENDPOINT")
    if endpoint:
        return endpoint

    return None


async def capture_page_traffic(
    url: str,
    wait_time_ms: int = 8000,
    use_browserless: bool = True,
    capture_tracking: bool = False,
    max_body_size: int = 10_000_000,  # 10MB
) -> CapturedTraffic:
    """Capture all network traffic when loading a page.

    Args:
        url: The URL to load.
        wait_time_ms: Time to wait for XHR requests after load (ms).
        use_browserless: Whether to use Browserless.io (if available).
        capture_tracking: Whether to capture tracking/analytics requests.
        max_body_size: Maximum body size to capture (bytes).

    Returns:
        CapturedTraffic with all captured resources.
    """
    import time

    traffic = CapturedTraffic(page_url=url)
    start_time = time.time()

    # Store responses for body capture
    response_bodies: dict[str, str] = {}
    request_timings: dict[str, float] = {}

    async def handle_response(response: Response) -> None:
        """Capture response body for relevant requests."""
        try:
            req_url = response.url

            # Skip tracking unless requested
            if not capture_tracking and _is_tracking_url(req_url):
                return

            content_type = response.headers.get("content-type", "")
            playwright_type = response.request.resource_type
            resource_type = _classify_resource_type(
                playwright_type, content_type, req_url
            )

            # Only capture body for relevant types
            if _should_capture_body(resource_type, content_type):
                try:
                    body = await response.text()
                    if body and len(body) <= max_body_size:
                        response_bodies[req_url] = body
                except Exception:
                    pass

        except Exception:
            pass

    async with async_playwright() as p:
        # Connect to browser
        browserless_endpoint = get_browserless_endpoint() if use_browserless else None

        if browserless_endpoint:
            try:
                browser = await p.chromium.connect_over_cdp(browserless_endpoint)
            except Exception as e:
                traffic.errors.append(f"Browserless connection failed: {e}")
                browser = await p.chromium.launch(headless=True)
        else:
            browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            # Track all requests
            resources: list[CapturedResource] = []

            async def on_request(request: Request) -> None:
                request_timings[request.url] = time.time()

            async def on_response(response: Response) -> None:
                try:
                    req = response.request
                    req_url = req.url

                    # Skip tracking unless requested
                    if not capture_tracking and _is_tracking_url(req_url):
                        return

                    content_type = response.headers.get("content-type", "")
                    playwright_type = req.resource_type
                    resource_type = _classify_resource_type(
                        playwright_type, content_type, req_url
                    )

                    # Calculate timing
                    timing = None
                    if req_url in request_timings:
                        timing = (time.time() - request_timings[req_url]) * 1000

                    resource = CapturedResource(
                        url=req_url,
                        method=req.method,
                        resource_type=resource_type,
                        content_type=content_type,
                        status_code=response.status,
                        request_headers=dict(req.headers),
                        response_headers=dict(response.headers),
                        body=None,  # Will be filled later
                        body_size=0,
                        timing_ms=timing,
                    )
                    resources.append(resource)

                except Exception:
                    pass

                # Also handle body capture
                await handle_response(response)

            page.on("request", on_request)
            page.on("response", on_response)

            # Navigate to the page
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                traffic.errors.append(f"Page load issue: {e}")

            # Wait for additional XHR requests
            await page.wait_for_timeout(wait_time_ms)

            # Capture final state
            traffic.final_url = page.url
            traffic.page_html = await page.content()
            traffic.load_time_ms = (time.time() - start_time) * 1000

            # Attach bodies to resources
            for resource in resources:
                if resource.url in response_bodies:
                    resource.body = response_bodies[resource.url]
                    resource.body_size = len(resource.body)

            traffic.resources = resources

        finally:
            await browser.close()

    return traffic
