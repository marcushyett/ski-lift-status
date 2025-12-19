"""Network traffic capture module.

Captures XHR requests, JavaScript files, HTML content, and other resources
from ski resort status pages using the XHR Fetcher API.
"""

from .traffic_capture import (
    CapturedResource,
    ResourceType,
    CapturedTraffic,
    capture_page_traffic,
    capture_iframe_traffic,
)

__all__ = [
    "CapturedResource",
    "ResourceType",
    "CapturedTraffic",
    "capture_page_traffic",
    "capture_iframe_traffic",
]
