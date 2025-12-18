"""
Skiplan platform adapter.

Skiplan is a resort management system used by many French ski resorts.
It provides lift/run status through XHR responses (getOuvertures.php).

Known URL patterns:
- live.skiplan.com/moduleweb/2.0/live.php?resort={resort}&module=ouvertures
- live.skiplan.com/moduleweb/2.0/php/getOuvertures.php?resort={resort}

Extraction approach:
The actual lift/run data is in the getOuvertures.php response, which contains
HTML with .ouvertures-marker elements. Each marker has:
- .marker-title with name and type icon (piste-verte.svg, etc.)
- .marker-content with status (.close, .open, .warning classes)
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from ..logging_config import get_logger
from ..models import CapturedResource

logger = get_logger(__name__)


@dataclass
class SkiplanLift:
    """Lift data from Skiplan."""

    name: str
    status: str | None
    lift_type: str | None
    sector: str | None = None


@dataclass
class SkiplanTrail:
    """Trail data from Skiplan."""

    name: str
    status: str | None
    difficulty: str | None
    sector: str | None = None


@dataclass
class SkiplanData:
    """Extracted data from Skiplan platform."""

    lifts: list[SkiplanLift]
    trails: list[SkiplanTrail]
    resort_id: str | None = None


# URL patterns that indicate Skiplan platform
URL_PATTERNS: list[str] = [
    r"live\.skiplan\.com/moduleweb",
    r"skiplan\.com/api",
    r"skiplan\.com/live",
]

# Mapping of SVG icon names to difficulty levels
# Use specific patterns to avoid false matches (e.g., "black" would match "prl_tc_black.svg")
DIFFICULTY_MAP: dict[str, str] = {
    "piste-verte": "easy",
    "piste-bleue": "intermediate",
    "piste-rouge": "advanced",
    "piste-noire": "expert",
    "piste_verte": "easy",
    "piste_bleue": "intermediate",
    "piste_rouge": "advanced",
    "piste_noire": "expert",
    # Only match standalone color names with piste prefix or explicit trail markers
    "trail-green": "easy",
    "trail-blue": "intermediate",
    "trail-red": "advanced",
    "trail-black": "expert",
    "run-green": "easy",
    "run-blue": "intermediate",
    "run-red": "advanced",
    "run-black": "expert",
}

# Mapping of SVG icon names to lift types
# Order matters - longer/more specific patterns first to avoid substring false matches
LIFT_TYPE_MAP: list[tuple[str, str]] = [
    # Explicit prl_ prefixed patterns (La Plagne and other resorts)
    ("prl_tsd", "télésiège débrayable"),
    ("prl_tlc", "télécabine"),
    ("prl_tph", "téléphérique"),
    ("prl_tc", "télécabine"),
    ("prl_ts", "télésiège"),
    ("prl_tk", "téléski"),
    ("prl_tapis", "tapis roulant"),
    # Generic patterns (must check tsd before ts to avoid false match)
    ("funitel", "funitel"),
    ("tapis", "tapis roulant"),
    ("tsd", "télésiège débrayable"),
    ("tlc", "télécabine"),
    ("tph", "téléphérique"),
    ("tc", "télécabine"),
    ("ts", "télésiège"),
    ("tk", "téléski"),
    ("tp", "téléphérique"),
    ("tf", "funiculaire"),
    # Alternative naming patterns
    ("telecabine", "télécabine"),
    ("telesiege", "télésiège"),
    ("teleski", "téléski"),
    ("telepherique", "téléphérique"),
    ("funicular", "funiculaire"),
    ("gondola", "télécabine"),
    ("chairlift", "télésiège"),
    ("draglift", "téléski"),
]


def detect(resources: list[CapturedResource]) -> bool:
    """Check if any resources match Skiplan platform patterns."""
    for resource in resources:
        for pattern in URL_PATTERNS:
            if re.search(pattern, resource.url, re.IGNORECASE):
                return True
    return False


def _find_ouvertures_response(resources: list[CapturedResource]) -> CapturedResource | None:
    """Find the getOuvertures.php response which contains the actual data."""
    for resource in resources:
        if "getOuvertures.php" in resource.url:
            return resource
    return None


def _find_main_page(resources: list[CapturedResource]) -> CapturedResource | None:
    """Find the main skiplan live.php page (fallback)."""
    for resource in resources:
        if "live.php" in resource.url and "skiplan.com" in resource.url:
            return resource
    return None


def _get_classes(element: Tag) -> list[str]:
    """Safely get classes from an element as a list of strings."""
    classes = element.get("class")
    if classes is None:
        return []
    if isinstance(classes, list):
        return [str(c) for c in classes]
    return [str(classes)]


def _extract_status_from_marker(marker: Tag) -> str:
    """Extract status from a marker element.

    Status is determined by:
    1. Classes on .marker-content children (.close, .open, .warning)
    2. Text content like "closed", "open", etc.
    """
    content = marker.select_one(".marker-content")
    if not content:
        return "unknown"

    # Check for status classes on child elements
    for child in content.find_all(True):
        if not isinstance(child, Tag):
            continue
        classes = _get_classes(child)
        if "close" in classes or "closed" in classes:
            return "closed"
        if "open" in classes or "opened" in classes:
            return "open"
        if "warning" in classes:
            # Check text for more specific status
            text = child.get_text(strip=True).lower()
            if "closed" in text or "fermé" in text or "ferme" in text:
                return "closed"
            if "waiting" in text or "attente" in text:
                return "waiting"
            return "warning"
        if "waiting" in classes:
            return "waiting"

    # Check text content
    text = content.get_text(strip=True).lower()
    if "closed" in text or "fermé" in text:
        return "closed"
    if "open" in text or "ouvert" in text:
        return "open"

    return "unknown"


def _extract_type_from_icon(marker: Tag) -> tuple[str | None, str | None]:
    """Extract type and difficulty from the icon image in marker-title.

    Returns (item_type, difficulty) where:
    - item_type is 'lift' or 'trail'
    - difficulty is the trail difficulty (for trails) or lift type (for lifts)
    """
    title = marker.select_one(".marker-title")
    if not title:
        return None, None

    # Find the img element
    img = title.select_one("img")
    if not img:
        return None, None

    src = img.get("src", "")
    if isinstance(src, list):
        src = src[0] if src else ""
    src = str(src).lower()

    # Check for lift types FIRST (prl_ prefix is distinctive for lifts)
    # Order matters - longer/more specific patterns first
    for pattern, lift_type in LIFT_TYPE_MAP:
        if pattern in src:
            return "lift", lift_type

    # Check for trail types (use specific piste- patterns)
    for pattern, difficulty in DIFFICULTY_MAP.items():
        if pattern in src:
            return "trail", difficulty

    # Default heuristics based on filename
    if "prl_" in src or "rm" in src or "lift" in src or "remontee" in src:
        # prl_ prefix usually indicates lift markers
        return "lift", None
    if "piste" in src or "trail" in src or "run" in src:
        return "trail", None

    return None, None


def _extract_name_from_marker(marker: Tag) -> str | None:
    """Extract the name from a marker element.

    The name is in .marker-title, after any img tags.
    """
    title = marker.select_one(".marker-title")
    if not title:
        return None

    # Get text content, excluding nested elements with class toggle-marker
    # The name is typically right after the img tag
    text_parts = []
    for child in title.children:
        if isinstance(child, str):
            text_parts.append(child.strip())
        elif isinstance(child, Tag):
            if child.name == "img":
                continue  # Skip images
            if "toggle-marker" in _get_classes(child):
                continue  # Skip toggle button
            text_parts.append(child.get_text(strip=True))

    name = " ".join(text_parts).strip()

    # Clean up the name
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
    name = name.strip()

    return name if name else None


def _parse_ouvertures_html(html: str) -> tuple[list[SkiplanLift], list[SkiplanTrail]]:
    """Parse the getOuvertures.php HTML response."""
    soup = BeautifulSoup(html, "lxml")

    lifts: list[SkiplanLift] = []
    trails: list[SkiplanTrail] = []

    # Find all markers
    markers = soup.select(".ouvertures-marker")

    for marker in markers:
        if not isinstance(marker, Tag):
            continue

        name = _extract_name_from_marker(marker)
        if not name:
            continue

        status = _extract_status_from_marker(marker)
        item_type, type_info = _extract_type_from_icon(marker)

        if item_type == "lift":
            lifts.append(SkiplanLift(
                name=name,
                status=status,
                lift_type=type_info,
                sector=None,
            ))
        elif item_type == "trail":
            trails.append(SkiplanTrail(
                name=name,
                status=status,
                difficulty=type_info,
                sector=None,
            ))
        else:
            # Unknown type - try to guess from name
            name_lower = name.lower()
            if any(kw in name_lower for kw in ["télésiège", "télécabine", "téléski", "tapis"]):
                lifts.append(SkiplanLift(
                    name=name,
                    status=status,
                    lift_type=None,
                    sector=None,
                ))
            else:
                # Default to trail
                trails.append(SkiplanTrail(
                    name=name,
                    status=status,
                    difficulty=None,
                    sector=None,
                ))

    # Deduplicate by name
    seen_lift_names: set[str] = set()
    unique_lifts = []
    for lift in lifts:
        if lift.name not in seen_lift_names:
            seen_lift_names.add(lift.name)
            unique_lifts.append(lift)

    seen_trail_names: set[str] = set()
    unique_trails = []
    for trail in trails:
        if trail.name not in seen_trail_names:
            seen_trail_names.add(trail.name)
            unique_trails.append(trail)

    return unique_lifts, unique_trails


def extract(resources: list[CapturedResource]) -> SkiplanData | None:
    """Extract lift/run data from Skiplan platform.

    The actual data is in the getOuvertures.php XHR response,
    which contains HTML with .ouvertures-marker elements.

    Args:
        resources: List of captured network resources

    Returns:
        SkiplanData with extracted lifts and trails, or None if extraction fails
    """
    log = logger.bind(adapter="skiplan")

    # First try to find the getOuvertures.php response
    ouvertures = _find_ouvertures_response(resources)
    if ouvertures and ouvertures.content:
        log.info("found_ouvertures_response", url=ouvertures.url[:80])
        lifts, trails = _parse_ouvertures_html(ouvertures.content)

        # Extract resort ID from URL
        resort_id = None
        match = re.search(r"resort=([^&]+)", ouvertures.url)
        if match:
            resort_id = match.group(1)

        log.info(
            "extraction_complete",
            lift_count=len(lifts),
            trail_count=len(trails),
        )

        return SkiplanData(lifts=lifts, trails=trails, resort_id=resort_id)

    # Fallback to main page (though this likely won't have the data)
    main_page = _find_main_page(resources)
    if not main_page:
        log.warning("no_skiplan_data", msg="Neither getOuvertures.php nor live.php found")
        return None

    log.warning("no_ouvertures_response", msg="getOuvertures.php not found, using live.php")

    html = main_page.content or ""
    if not html:
        log.warning("empty_content", msg="Skiplan page has no content")
        return None

    lifts, trails = _parse_ouvertures_html(html)

    # Extract resort ID from URL
    resort_id = None
    match = re.search(r"resort=([^&]+)", main_page.url)
    if match:
        resort_id = match.group(1)

    log.info(
        "extraction_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return SkiplanData(lifts=lifts, trails=trails, resort_id=resort_id)


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
