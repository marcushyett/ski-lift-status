"""Page loader module using Playwright for capturing network traffic."""

import asyncio
import time
from typing import Callable

from playwright.async_api import Response, async_playwright

from .logging_config import get_logger, save_debug_artifact
from .models import CapturedResource, NetworkCapture, ResourceType

logger = get_logger(__name__)


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
    """Loads pages and captures network traffic using Playwright."""

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
        responses: dict[str, Response] = {}
        all_urls_seen: list[str] = []

        async with async_playwright() as p:
            log.debug("launching_browser", headless=self.headless)
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

            except Exception as e:
                error_msg = f"Error loading page: {str(e)}"
                capture.errors.append(error_msg)
                log.error("page_load_failed", error=str(e))

            finally:
                await browser.close()

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
        max_concurrent: int = 3,
    ) -> list[NetworkCapture]:
        """Load multiple pages concurrently.

        Args:
            pages: List of (url, resort_id) tuples.
            max_concurrent: Maximum concurrent page loads.

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
