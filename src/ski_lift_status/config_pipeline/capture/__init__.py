"""Network traffic capture module.

Captures XHR requests, JavaScript files, HTML content, and other resources
from ski resort status pages using Playwright with Browserless.
"""

from .traffic_capture import (
    CapturedResource,
    ResourceType,
    CapturedTraffic,
    capture_page_traffic,
)

__all__ = [
    "CapturedResource",
    "ResourceType",
    "CapturedTraffic",
    "capture_page_traffic",
]
