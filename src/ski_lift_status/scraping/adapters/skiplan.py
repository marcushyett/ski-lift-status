"""
Skiplan platform adapter.

Skiplan is a resort management system used by many French ski resorts.
It provides lift/run status through server-side rendered HTML pages
embedded via iframes.

Known URL patterns:
- live.skiplan.com/moduleweb/2.0/live.php?resort={resort}&module=ouvertures
- skiplan.com/api/

Extraction approach:
The skiplan pages are server-side rendered with structured HTML.
We use CSS selectors to extract lift/run data from the DOM:
- Lift/run items are in structured elements with status classes
- Status is indicated via CSS classes (ouvert, ferme, etc.)
- Names and types are in child elements
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

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
URL_PATTERNS = [
    r"live\.skiplan\.com/moduleweb",
    r"skiplan\.com/api",
    r"skiplan\.com/live",
]

# CSS selectors for different element types
LIFT_SELECTORS = [
    ".rm-item",  # Common lift item class
    ".remontee-item",
    "[data-type='remontee']",
    ".lift-item",
    ".rm",  # Short form
]

TRAIL_SELECTORS = [
    ".piste-item",
    "[data-type='piste']",
    ".trail-item",
    ".piste",
]

# Status class patterns
STATUS_PATTERNS = {
    "open": ["ouvert", "open", "status-o", "status-1", "opened"],
    "closed": ["ferme", "fermé", "closed", "status-f", "status-0"],
    "forecast": ["prevision", "forecast", "status-p", "planned"],
    "maintenance": ["maintenance", "entretien"],
}


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


def _get_status_from_classes(classes: list[str]) -> str | None:
    """Determine status from CSS classes."""
    class_str = " ".join(classes).lower()

    for status, patterns in STATUS_PATTERNS.items():
        for pattern in patterns:
            if pattern in class_str:
                return status

    return None


def _get_status_from_element(element: BeautifulSoup) -> str | None:
    """Extract status from an element or its children."""
    # Check element's own classes
    classes = element.get("class", [])
    status = _get_status_from_classes(classes)
    if status:
        return status

    # Check for status child element
    status_elem = element.select_one(".status, .etat, [class*='status']")
    if status_elem:
        status = _get_status_from_classes(status_elem.get("class", []))
        if status:
            return status

        # Check text content
        text = status_elem.get_text(strip=True).lower()
        for status_name, patterns in STATUS_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    return status_name

    return None


def _extract_name(element: BeautifulSoup) -> str | None:
    """Extract name from an element."""
    # Try common name selectors
    name_selectors = [
        ".name",
        ".nom",
        ".title",
        ".titre",
        "h3",
        "h4",
        ".label",
        "[class*='name']",
        "[class*='nom']",
    ]

    for selector in name_selectors:
        name_elem = element.select_one(selector)
        if name_elem:
            name = name_elem.get_text(strip=True)
            if name:
                return name

    # Try data attributes
    for attr in ["data-name", "data-nom", "data-title", "title"]:
        name = element.get(attr)
        if name:
            return name

    # Fall back to element text
    text = element.get_text(strip=True)
    if text and len(text) < 100:  # Reasonable name length
        return text

    return None


def _extract_lift_type(element: BeautifulSoup) -> str | None:
    """Extract lift type from an element."""
    type_selectors = [".type", ".category", "[class*='type']"]

    for selector in type_selectors:
        type_elem = element.select_one(selector)
        if type_elem:
            return type_elem.get_text(strip=True)

    # Check for type in classes
    classes = element.get("class", [])
    lift_types = {
        "tc": "télécabine",
        "tsd": "télésiège débrayable",
        "ts": "télésiège",
        "tk": "téléski",
        "tp": "téléphérique",
        "tf": "funiculaire",
        "tb": "tapis",
    }

    for cls in classes:
        cls_lower = cls.lower()
        for abbrev, full_name in lift_types.items():
            if cls_lower.startswith(abbrev) or abbrev in cls_lower:
                return full_name

    return None


def _extract_difficulty(element: BeautifulSoup) -> str | None:
    """Extract trail difficulty from an element."""
    # Check for difficulty classes
    classes = element.get("class", [])
    class_str = " ".join(classes).lower()

    difficulties = {
        "verte": "easy",
        "green": "easy",
        "bleue": "intermediate",
        "blue": "intermediate",
        "rouge": "advanced",
        "red": "advanced",
        "noire": "expert",
        "black": "expert",
    }

    for color, difficulty in difficulties.items():
        if color in class_str:
            return difficulty

    # Check for difficulty element
    diff_elem = element.select_one(".difficulty, .difficulte, [class*='diff']")
    if diff_elem:
        text = diff_elem.get_text(strip=True).lower()
        for color, difficulty in difficulties.items():
            if color in text:
                return difficulty

    return None


def _extract_sector(element: BeautifulSoup) -> str | None:
    """Extract sector/zone from an element."""
    sector_selectors = [".sector", ".secteur", ".zone", "[class*='sector']"]

    for selector in sector_selectors:
        sector_elem = element.select_one(selector)
        if sector_elem:
            return sector_elem.get_text(strip=True)

    return element.get("data-sector") or element.get("data-secteur")


def _extract_lifts(soup: BeautifulSoup) -> list[SkiplanLift]:
    """Extract all lifts from the page."""
    lifts = []

    for selector in LIFT_SELECTORS:
        elements = soup.select(selector)
        for elem in elements:
            name = _extract_name(elem)
            if not name:
                continue

            lifts.append(
                SkiplanLift(
                    name=name,
                    status=_get_status_from_element(elem),
                    lift_type=_extract_lift_type(elem),
                    sector=_extract_sector(elem),
                )
            )

    # Deduplicate by name
    seen_names: set[str] = set()
    unique_lifts = []
    for lift in lifts:
        if lift.name not in seen_names:
            seen_names.add(lift.name)
            unique_lifts.append(lift)

    return unique_lifts


def _extract_trails(soup: BeautifulSoup) -> list[SkiplanTrail]:
    """Extract all trails from the page."""
    trails = []

    for selector in TRAIL_SELECTORS:
        elements = soup.select(selector)
        for elem in elements:
            name = _extract_name(elem)
            if not name:
                continue

            trails.append(
                SkiplanTrail(
                    name=name,
                    status=_get_status_from_element(elem),
                    difficulty=_extract_difficulty(elem),
                    sector=_extract_sector(elem),
                )
            )

    # Deduplicate by name
    seen_names: set[str] = set()
    unique_trails = []
    for trail in trails:
        if trail.name not in seen_names:
            seen_names.add(trail.name)
            unique_trails.append(trail)

    return unique_trails


def extract(resources: list[CapturedResource]) -> SkiplanData | None:
    """Extract lift/run data from Skiplan platform using CSS selectors.

    Skiplan pages are server-side rendered, so we can parse the HTML
    directly using BeautifulSoup and CSS selectors.

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
    if not html:
        log.warning("empty_content", msg="Skiplan page has no content")
        return None

    soup = BeautifulSoup(html, "lxml")

    # Extract lifts and trails
    lifts = _extract_lifts(soup)
    trails = _extract_trails(soup)

    log.info(
        "extraction_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    # Extract resort ID from URL if possible
    resort_id = None
    match = re.search(r"resort=([^&]+)", main_page.url)
    if match:
        resort_id = match.group(1)

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
