"""
Skiplan platform adapter.

Skiplan is a resort management system used by many French ski resorts.
It provides lift/run status through an embedded iframe that renders
data using JavaScript/SVG/Canvas.

Known URL patterns:
- live.skiplan.com/moduleweb/2.0/live.php?resort={resort}&module=ouvertures
- skiplan.com/api/

The data is NOT available as JSON - it's rendered client-side from
JavaScript variables and function calls like gotoPictoPrl().

Extraction approach:
1. Parse JavaScript for gotoPictoPrl() calls which contain lift names
2. Parse embedded HTML for status classes
3. Extract data from SVG/Canvas elements

TODO: This adapter requires additional work to fully implement.
"""

import re
from dataclasses import dataclass
from typing import Any

from ..models import CapturedResource
from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SkiplanLift:
    """Lift data from Skiplan."""

    name: str
    status: str | None
    lift_type: str | None


@dataclass
class SkiplanTrail:
    """Trail data from Skiplan."""

    name: str
    status: str | None
    difficulty: str | None


@dataclass
class SkiplanData:
    """Extracted data from Skiplan platform."""

    lifts: list[SkiplanLift]
    trails: list[SkiplanTrail]
    resort_id: str | None = None


# URL patterns that indicate Skiplan platform
URL_PATTERNS = [
    r"live\.skiplan\.com/moduleweb",
    r"skiplan\.com/api",
    r"skiplan\.com/live",
]


def detect(resources: list[CapturedResource]) -> bool:
    """Check if any resources match Skiplan platform patterns."""
    for resource in resources:
        for pattern in URL_PATTERNS:
            if re.search(pattern, resource.url, re.IGNORECASE):
                return True
    return False


def find_main_page(resources: list[CapturedResource]) -> CapturedResource | None:
    """Find the main skiplan live.php page."""
    for resource in resources:
        if "live.php" in resource.url and "skiplan.com" in resource.url:
            return resource
    return None


def extract_lift_names_from_js(js_content: str) -> list[str]:
    """Extract lift names from gotoPictoPrl() JavaScript calls.

    The skiplan JavaScript contains calls like:
    gotoPictoPrl("picto_TC DES VERDONS", false, 0.5, true, 3640, 1035);

    We extract the lift names from these calls.
    """
    pattern = r'gotoPictoPrl\("picto_([^"]+)"'
    matches = re.findall(pattern, js_content)
    return matches


def parse_status_from_html(html: str) -> dict[str, str]:
    """Parse status indicators from HTML.

    Skiplan uses CSS classes like:
    - 'ouvert' / 'open' for open
    - 'ferme' / 'closed' for closed
    - 'prevision' for forecast

    Returns mapping of lift/run names to status.
    """
    # This is a stub - full implementation requires parsing
    # the complex SVG/canvas structure
    return {}


def extract(resources: list[CapturedResource]) -> SkiplanData | None:
    """Extract lift/run data from Skiplan platform.

    Note: Skiplan data extraction is complex because:
    1. Data is rendered client-side via JavaScript
    2. Status is shown via SVG/Canvas graphics
    3. No clean JSON API is available

    This adapter provides basic extraction from JavaScript and HTML.
    For full extraction, the page must be rendered with a browser.

    Args:
        resources: List of captured network resources

    Returns:
        SkiplanData with extracted lifts and trails, or None if extraction fails
    """
    log = logger.bind(adapter="skiplan")

    main_page = find_main_page(resources)
    if not main_page:
        log.warning("no_main_page", msg="Skiplan live.php page not found")
        return None

    html = main_page.content or ""

    # Extract lift names from JavaScript
    lift_names = extract_lift_names_from_js(html)
    log.info("js_lift_names_found", count=len(lift_names))

    # Try to parse status from HTML
    status_map = parse_status_from_html(html)

    lifts = []
    for name in lift_names:
        lifts.append(
            SkiplanLift(
                name=name,
                status=status_map.get(name),
                lift_type=None,  # Would need to parse from HTML
            )
        )

    log.info(
        "extraction_complete",
        lift_count=len(lifts),
        trail_count=0,
        note="Skiplan extraction is limited without full JS rendering",
    )

    return SkiplanData(lifts=lifts, trails=[], resort_id=None)


def get_status_summary(data: SkiplanData) -> dict[str, dict[str, int]]:
    """Get aggregate status counts."""
    lift_status: dict[str, int] = {}
    trail_status: dict[str, int] = {}

    for lift in data.lifts:
        status = lift.status or "unknown"
        lift_status[status] = lift_status.get(status, 0) + 1

    for trail in data.trails:
        status = trail.status or "unknown"
        trail_status[status] = trail_status.get(status, 0) + 1

    return {"lifts": lift_status, "trails": trail_status}
