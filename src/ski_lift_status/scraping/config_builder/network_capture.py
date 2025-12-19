"""Network traffic capture using Playwright with Browserless."""

import os
import re
from dataclasses import dataclass, field

import structlog
from playwright.async_api import async_playwright, Response, Request

logger = structlog.get_logger()


@dataclass
class CapturedRequest:
    """A captured network request."""

    url: str
    method: str
    resource_type: str
    status: int | None = None
    content_type: str | None = None
    content: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class NetworkTraffic:
    """Captured network traffic from a page load."""

    page_url: str
    requests: list[CapturedRequest] = field(default_factory=list)
    final_url: str | None = None  # After redirects
    page_content: str | None = None
    errors: list[str] = field(default_factory=list)


def get_browserless_endpoint() -> str | None:
    """Get Browserless WebSocket endpoint from environment."""
    # Check for Browserless API key
    api_key = os.environ.get("BROWSERLESS_API_KEY")
    if api_key:
        return f"wss://chrome.browserless.io?token={api_key}"

    # Check for custom endpoint
    endpoint = os.environ.get("BROWSERLESS_ENDPOINT")
    if endpoint:
        return endpoint

    return None


async def capture_network_traffic(
    url: str,
    wait_time: int = 5000,
    use_browserless: bool = True,
) -> NetworkTraffic:
    """Capture all network traffic when loading a page.

    Args:
        url: The URL to load.
        wait_time: Time to wait for XHR requests (ms).
        use_browserless: Whether to use Browserless.io (if available).

    Returns:
        NetworkTraffic with all captured requests.
    """
    log = logger.bind(url=url[:80])
    traffic = NetworkTraffic(page_url=url)

    # Response bodies we want to capture
    captured_responses: dict[str, str] = {}

    async def handle_response(response: Response) -> None:
        """Capture response content for relevant requests."""
        try:
            url = response.url
            content_type = response.headers.get("content-type", "")

            # Only capture JSON, HTML, and JavaScript responses
            if any(ct in content_type for ct in ["json", "html", "javascript", "text"]):
                try:
                    body = await response.text()
                    if body and len(body) < 5_000_000:  # Max 5MB
                        captured_responses[url] = body
                except Exception:
                    pass
        except Exception:
            pass

    async with async_playwright() as p:
        # Determine browser connection
        browserless_endpoint = get_browserless_endpoint() if use_browserless else None

        if browserless_endpoint:
            log.info("connecting_browserless")
            try:
                browser = await p.chromium.connect_over_cdp(browserless_endpoint)
            except Exception as e:
                log.warning("browserless_connection_failed", error=str(e))
                traffic.errors.append(f"Browserless connection failed: {e}")
                # Fall back to local browser
                browser = await p.chromium.launch(headless=True)
        else:
            log.info("using_local_browser")
            browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # Capture all requests
            requests_seen: list[CapturedRequest] = []

            async def on_request(request: Request) -> None:
                requests_seen.append(CapturedRequest(
                    url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                    headers=dict(request.headers),
                ))

            async def on_response(response: Response) -> None:
                # Update request with response info
                for req in requests_seen:
                    if req.url == response.url:
                        req.status = response.status
                        req.content_type = response.headers.get("content-type")
                        break
                # Also capture body
                await handle_response(response)

            page.on("request", on_request)
            page.on("response", on_response)

            # Navigate to the page
            log.info("loading_page")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                log.warning("page_load_timeout", error=str(e))
                traffic.errors.append(f"Page load issue: {e}")

            # Wait additional time for XHR requests
            await page.wait_for_timeout(wait_time)

            # Capture final state
            traffic.final_url = page.url
            traffic.page_content = await page.content()

            # Add captured content to requests
            for req in requests_seen:
                if req.url in captured_responses:
                    req.content = captured_responses[req.url]

            traffic.requests = requests_seen

            log.info(
                "capture_complete",
                request_count=len(requests_seen),
                with_content=len(captured_responses),
            )

        finally:
            await browser.close()

    return traffic


def filter_relevant_requests(traffic: NetworkTraffic) -> list[CapturedRequest]:
    """Filter to requests that are likely to contain lift/trail data.

    Returns requests that:
    - Are XHR/fetch requests (not images, fonts, etc.)
    - Return JSON or HTML
    - Have content that might contain lift data
    """
    relevant = []

    for req in traffic.requests:
        # Skip non-data resources
        if req.resource_type in ["image", "font", "stylesheet", "media"]:
            continue

        # Skip if no content
        if not req.content:
            continue

        # Skip tracking/analytics
        skip_patterns = [
            "google-analytics", "googletagmanager", "facebook",
            "doubleclick", "analytics", "tracking", "pixel",
            "hotjar", "clarity", "sentry", "bugsnag",
        ]
        if any(p in req.url.lower() for p in skip_patterns):
            continue

        # Check if content might have lift data
        content_lower = req.content.lower()
        lift_indicators = [
            "lift", "chairlift", "gondola", "telecabine", "telesiege",
            "télésiège", "télécabine", "téléski", "remontee", "impianti",
            "piste", "slope", "trail", "run", "open", "closed", "status",
        ]

        if any(indicator in content_lower for indicator in lift_indicators):
            relevant.append(req)

    return relevant
