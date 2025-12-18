"""Page loader module using Playwright for capturing network traffic."""

import asyncio
import time
from typing import Callable

from playwright.async_api import Page, Request, Response, async_playwright

from .models import CapturedResource, NetworkCapture, ResourceType


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
    api_patterns = ["/api/", "/data/", "/status/", "/lifts/", "/runs/"]
    if any(pattern in url.lower() for pattern in api_patterns):
        return True

    return False


class PageLoader:
    """Loads pages and captures network traffic using Playwright."""

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        wait_after_load_ms: int = 3000,
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
        capture = NetworkCapture(
            resort_id=resort_id,
            status_page_url=url,
        )

        start_time = time.time()
        responses: dict[str, Response] = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # Track responses
            async def handle_response(response: Response) -> None:
                responses[response.url] = response

            page.on("response", handle_response)

            try:
                # Navigate to page
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

                # Wait additional time for XHR requests to complete
                await asyncio.sleep(self.wait_after_load_ms / 1000)

                # Capture page HTML
                capture.page_html = await page.content()

                # Process captured responses
                for resp_url, response in responses.items():
                    try:
                        content_type = response.headers.get("content-type", "")

                        if not _is_relevant_resource(resp_url, content_type):
                            continue

                        # Get response body
                        try:
                            body = await response.text()
                        except Exception:
                            continue  # Skip if can't get body

                        resource = CapturedResource(
                            url=resp_url,
                            resource_type=_determine_resource_type(
                                content_type, resp_url
                            ),
                            content_type=content_type,
                            content=body,
                            size_bytes=len(body.encode("utf-8")),
                            response_status=response.status,
                            headers=dict(response.headers),
                        )

                        capture.resources.append(resource)

                        if on_resource:
                            on_resource(resource)

                    except Exception as e:
                        capture.errors.append(f"Error processing {resp_url}: {str(e)}")

            except Exception as e:
                capture.errors.append(f"Error loading page: {str(e)}")

            finally:
                await browser.close()

        capture.load_time_ms = (time.time() - start_time) * 1000

        return capture

    async def load_multiple_pages(
        self,
        pages: list[tuple[str, str]],  # List of (url, resort_id) tuples
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
