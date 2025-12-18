"""Page loader module using Playwright/Stagehand for capturing network traffic."""

import asyncio
import os
import time
from typing import Callable

from playwright.async_api import Response, async_playwright

from .logging_config import get_logger, save_debug_artifact
from .models import CapturedResource, NetworkCapture, ResourceType

logger = get_logger(__name__)


def _get_browserbase_config() -> tuple[str, str] | None:
    """Get Browserbase configuration from environment variables.

    Returns:
        Tuple of (api_key, project_id) if configured, None otherwise.
    """
    api_key = os.environ.get("BROWSERBASE_API_KEY")
    project_id = os.environ.get("BROWSERBASE_PROJECT_ID")

    if api_key and project_id:
        return (api_key, project_id)
    return None


def _determine_resource_type(content_type: str | None, url: str) -> ResourceType:
    """Determine the resource type based on content type and URL."""
    if content_type is None:
        content_type = ""

    content_type = content_type.lower()

    if "application/json" in content_type or url.endswith(".json"):
        return ResourceType.JSON
    elif "javascript" in content_type or url.endswith(".js"):
        return ResourceType.JAVASCRIPT
    elif "text/html" in content_type or url.endswith(".html"):
        return ResourceType.HTML
    elif "xhr" in content_type:
        return ResourceType.XHR

    return ResourceType.OTHER


def _is_relevant_resource(url: str, content_type: str | None) -> bool:
    """Check if a resource is relevant for scraping analysis."""
    if content_type is None:
        content_type = ""

    content_type = content_type.lower()

    # Include JSON, HTML, JavaScript, and XHR responses
    relevant_types = [
        "application/json",
        "text/json",
        "text/html",
        "application/javascript",
        "text/javascript",
        "application/x-javascript",
    ]

    if any(rt in content_type for rt in relevant_types):
        return True

    # Check URL patterns
    relevant_extensions = [".json", ".js", ".html"]
    if any(url.lower().endswith(ext) for ext in relevant_extensions):
        return True

    # Include API endpoints
    api_patterns = ["/api/", "/data/", "/status/", "/lifts/", "/runs/", "/pistes/", "/remontees/"]
    if any(pattern in url.lower() for pattern in api_patterns):
        return True

    return False


class PageLoader:
    """Loads pages and captures network traffic using Playwright or Stagehand."""

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        wait_after_load_ms: int = 5000,
    ):
        """Initialize the page loader.

        Args:
            headless: Whether to run browser in headless mode.
            timeout_ms: Page load timeout in milliseconds.
            wait_after_load_ms: Additional wait time after page load for XHR requests.
        """
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_after_load_ms = wait_after_load_ms

    async def _release_browserbase_session(
        self, session_id: str, api_key: str, project_id: str, log
    ) -> None:
        """Release a Browserbase session."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.browserbase.com/v1/sessions/{session_id}",
                    headers={
                        "x-bb-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    json={"status": "REQUEST_RELEASE", "projectId": project_id},
                    timeout=10.0,
                )
            log.debug("browserbase_session_released", session_id=session_id)
        except Exception as e:
            log.warning("failed_to_release_session", session_id=session_id, error=str(e))

    async def _load_with_browserbase(
        self,
        url: str,
        resort_id: str,
        capture: NetworkCapture,
        on_resource: Callable[[CapturedResource], None] | None,
    ) -> tuple[dict[str, Response], list[str]]:
        """Load page using Browserbase cloud browser via direct API.

        Returns:
            Tuple of (responses dict, all_urls_seen list)
        """
        import httpx

        log = logger.bind(resort_id=resort_id, url=url, phase="browserbase_load")

        browserbase_config = _get_browserbase_config()
        if not browserbase_config:
            raise ValueError("Browserbase credentials not configured")

        api_key, project_id = browserbase_config

        # Create session via REST API
        log.info("creating_browserbase_session", project_id=project_id)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.browserbase.com/v1/sessions",
                headers={
                    "x-bb-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={"projectId": project_id},
                timeout=30.0,
            )
            response.raise_for_status()
            session_data = response.json()

        session_id = session_data["id"]
        connect_url = session_data.get("connectUrl")
        if not connect_url:
            # Fallback to constructed URL if connectUrl not provided
            connect_url = f"wss://connect.browserbase.com?apiKey={api_key}&sessionId={session_id}"

        log.info("browserbase_session_created", session_id=session_id, region=session_data.get("region"))

        responses: dict[str, Response] = {}
        all_urls_seen: list[str] = []
        browser = None

        try:
            async with async_playwright() as p:
                log.debug("connecting_to_browserbase_cdp")
                browser = await p.chromium.connect_over_cdp(connect_url)
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else await context.new_page()

                # Track all responses
                async def handle_response(response: Response) -> None:
                    all_urls_seen.append(response.url)
                    responses[response.url] = response

                page.on("response", handle_response)

                log.debug("navigating_to_page", timeout_ms=self.timeout_ms)
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

                log.debug("waiting_for_xhr", wait_ms=self.wait_after_load_ms)
                await asyncio.sleep(self.wait_after_load_ms / 1000)

                # Capture page HTML
                capture.page_html = await page.content()
                html_size = len(capture.page_html.encode("utf-8"))
                log.debug("captured_page_html", size_bytes=html_size)

                # Process captured responses
                await self._process_responses(responses, capture, log, on_resource)

                # Close browser before releasing session
                await browser.close()
                browser = None

        finally:
            # Always release the session
            log.debug("releasing_browserbase_session")
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            await self._release_browserbase_session(session_id, api_key, project_id, log)

        return responses, all_urls_seen

    async def _load_with_local_playwright(
        self,
        url: str,
        resort_id: str,
        capture: NetworkCapture,
        on_resource: Callable[[CapturedResource], None] | None,
    ) -> tuple[dict[str, Response], list[str]]:
        """Load page using local Playwright browser.

        Returns:
            Tuple of (responses dict, all_urls_seen list)
        """
        log = logger.bind(resort_id=resort_id, url=url, phase="local_playwright")

        responses: dict[str, Response] = {}
        all_urls_seen: list[str] = []

        async with async_playwright() as p:
            log.debug("launching_local_browser", headless=self.headless)
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # Track all responses
            async def handle_response(response: Response) -> None:
                all_urls_seen.append(response.url)
                responses[response.url] = response

            page.on("response", handle_response)

            try:
                log.debug("navigating_to_page", timeout_ms=self.timeout_ms)
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

                log.debug("waiting_for_xhr", wait_ms=self.wait_after_load_ms)
                await asyncio.sleep(self.wait_after_load_ms / 1000)

                # Capture page HTML
                capture.page_html = await page.content()
                html_size = len(capture.page_html.encode("utf-8"))
                log.debug("captured_page_html", size_bytes=html_size)

                # Process captured responses
                await self._process_responses(responses, capture, log, on_resource)

            finally:
                await browser.close()

        return responses, all_urls_seen

    async def _process_responses(
        self,
        responses: dict[str, Response],
        capture: NetworkCapture,
        log,
        on_resource: Callable[[CapturedResource], None] | None,
    ) -> None:
        """Process captured responses and add relevant resources to capture."""
        relevant_count = 0
        skipped_count = 0

        for resp_url, response in responses.items():
            try:
                content_type = response.headers.get("content-type", "")

                if not _is_relevant_resource(resp_url, content_type):
                    skipped_count += 1
                    continue

                # Get response body
                try:
                    body = await response.text()
                except Exception as e:
                    log.debug("failed_to_get_body", url=resp_url, error=str(e))
                    continue

                resource_type = _determine_resource_type(content_type, resp_url)

                resource = CapturedResource(
                    url=resp_url,
                    resource_type=resource_type,
                    content_type=content_type,
                    content=body,
                    size_bytes=len(body.encode("utf-8")),
                    response_status=response.status,
                    headers=dict(response.headers),
                )

                capture.resources.append(resource)
                relevant_count += 1

                log.debug(
                    "captured_resource",
                    url=resp_url[:100],
                    type=resource_type.value,
                    size_bytes=resource.size_bytes,
                    status=response.status,
                )

                if on_resource:
                    on_resource(resource)

            except Exception as e:
                error_msg = f"Error processing {resp_url}: {str(e)}"
                capture.errors.append(error_msg)
                log.warning("resource_processing_error", url=resp_url, error=str(e))

        log.info(
            "page_load_complete",
            total_responses=len(responses),
            relevant_resources=relevant_count,
            skipped_resources=skipped_count,
        )

    async def load_page(
        self,
        url: str,
        resort_id: str,
        on_resource: Callable[[CapturedResource], None] | None = None,
    ) -> NetworkCapture:
        """Load a page and capture all network traffic.

        Args:
            url: The URL to load.
            resort_id: The resort ID for reference.
            on_resource: Optional callback for each captured resource.

        Returns:
            NetworkCapture containing all captured resources.
        """
        log = logger.bind(resort_id=resort_id, url=url, phase="page_load")
        log.info("starting_page_load")

        capture = NetworkCapture(
            resort_id=resort_id,
            status_page_url=url,
        )

        start_time = time.time()
        all_urls_seen: list[str] = []

        try:
            # Check for Browserbase credentials - use Stagehand if available
            browserbase_config = _get_browserbase_config()

            if browserbase_config:
                log.info("using_browserbase_cloud")
                _, all_urls_seen = await self._load_with_browserbase(
                    url, resort_id, capture, on_resource
                )
            else:
                log.info("using_local_playwright")
                _, all_urls_seen = await self._load_with_local_playwright(
                    url, resort_id, capture, on_resource
                )

        except Exception as e:
            error_msg = f"Error loading page: {str(e)}"
            capture.errors.append(error_msg)
            log.error("page_load_failed", error=str(e))

        capture.load_time_ms = (time.time() - start_time) * 1000

        log.info(
            "capture_complete",
            load_time_ms=capture.load_time_ms,
            resource_count=len(capture.resources),
            error_count=len(capture.errors),
        )

        # Save debug artifacts
        save_debug_artifact(
            "network_capture",
            {
                "url": url,
                "resource_count": len(capture.resources),
                "resources": [
                    {
                        "url": r.url,
                        "type": r.resource_type.value,
                        "size": r.size_bytes,
                        "content_type": r.content_type,
                    }
                    for r in capture.resources
                ],
                "all_urls_seen": all_urls_seen[:100],  # First 100 for debugging
                "errors": capture.errors,
            },
            resort_id=resort_id,
            phase="phase1_capture",
        )

        return capture

    async def load_multiple_pages(
        self,
        pages: list[tuple[str, str]],
        max_concurrent: int = 1,  # Default to 1 for Browserbase free tier
    ) -> list[NetworkCapture]:
        """Load multiple pages sequentially (or with limited concurrency).

        Args:
            pages: List of (url, resort_id) tuples.
            max_concurrent: Maximum concurrent page loads (default 1 for Browserbase).

        Returns:
            List of NetworkCapture objects.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def load_with_semaphore(url: str, resort_id: str) -> NetworkCapture:
            async with semaphore:
                return await self.load_page(url, resort_id)

        tasks = [load_with_semaphore(url, resort_id) for url, resort_id in pages]
        return await asyncio.gather(*tasks)


async def capture_page_resources(
    url: str,
    resort_id: str,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> NetworkCapture:
    """Convenience function to capture resources from a single page.

    Args:
        url: The URL to load.
        resort_id: The resort ID for reference.
        headless: Whether to run browser in headless mode.
        timeout_ms: Page load timeout in milliseconds.

    Returns:
        NetworkCapture containing all captured resources.
    """
    loader = PageLoader(headless=headless, timeout_ms=timeout_ms)
    return await loader.load_page(url, resort_id)
