"""
Vail Resorts platform adapter.

Vail Resorts owns many ski resorts including:
- Breckenridge, Vail, Beaver Creek, Keystone (Colorado)
- Park City (Utah)
- Whistler Blackcomb (BC, Canada)
- Stowe, Okemo (Vermont)
- And many others

Their websites embed lift/terrain status in a JavaScript object called
`TerrainStatusFeed` which is included in a script tag on the page.

Extraction approach:
1. Fetch the terrain-and-lift-status.aspx page (using curl to bypass TLS fingerprinting)
2. Check for waiting room redirect and follow if needed
3. Find the script containing "TerrainStatusFeed = {"
4. Parse the JavaScript object to extract lift names and statuses
5. Status codes are numeric: 0=closed, 1=open, 2=hold, 3=scheduled

Based on the parsing logic from: https://github.com/pirxpilot/liftie
"""

import asyncio
import re
import json
import subprocess
from dataclasses import dataclass

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)


@dataclass
class VailLift:
    """Lift data from Vail Resorts."""
    name: str
    status: str | None
    lift_type: str | None = None
    wait_time: int | None = None
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class VailTrail:
    """Trail data from Vail Resorts."""
    name: str
    status: str | None
    difficulty: str | None = None
    grooming: str | None = None
    opening_time: str | None = None
    closing_time: str | None = None


@dataclass
class VailData:
    """Extracted data from Vail Resorts."""
    lifts: list[VailLift]
    trails: list[VailTrail]
    resort_name: str | None = None


# Status code mapping (from Liftie: lib/tools/vail.js)
STATUS_MAP = {
    0: "closed",
    1: "open",
    2: "hold",
    3: "scheduled",
}


def _extract_terrain_status_feed(html: str) -> dict | None:
    """Extract the TerrainStatusFeed JavaScript object from HTML.

    Args:
        html: The HTML content of the page

    Returns:
        Parsed dict from the TerrainStatusFeed object, or None if not found
    """
    log = logger.bind(adapter="vail")

    # Find the script containing TerrainStatusFeed
    # Pattern: TerrainStatusFeed = {...}
    pattern = r'TerrainStatusFeed\s*=\s*(\{[^;]+\});'

    match = re.search(pattern, html, re.DOTALL)
    if not match:
        log.debug("terrain_status_feed_not_found")
        return None

    js_object = match.group(1)

    # Try to parse as JSON - may need some cleanup
    try:
        # The object might not be valid JSON (single quotes, trailing commas)
        # Try to clean it up

        # Replace single quotes with double quotes (careful with nested quotes)
        # This is a simple approach - might need refinement
        cleaned = js_object

        # Try direct JSON parse first
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.debug("json_parse_failed_trying_cleanup")

    # Try alternative approach: use regex to extract key-value pairs
    # For lift status, we mainly need the Lifts array
    lifts_pattern = r'"?Lifts"?\s*:\s*\[([^\]]+)\]'
    lifts_match = re.search(lifts_pattern, html, re.DOTALL)

    if lifts_match:
        lifts_str = lifts_match.group(1)
        # Try to parse individual lift objects
        lift_pattern = r'\{[^}]+\}'
        lift_objects = re.findall(lift_pattern, lifts_str)

        lifts = []
        for obj_str in lift_objects:
            # Extract name and status
            name_match = re.search(r'"?Name"?\s*:\s*"([^"]+)"', obj_str)
            status_match = re.search(r'"?Status"?\s*:\s*(\d)', obj_str)

            if name_match:
                lift = {"Name": name_match.group(1)}
                if status_match:
                    lift["Status"] = int(status_match.group(1))
                lifts.append(lift)

        if lifts:
            return {"Lifts": lifts}

    return None


def _parse_terrain_data(data: dict) -> tuple[list[VailLift], list[VailTrail]]:
    """Parse the TerrainStatusFeed data into lift and trail objects.

    Args:
        data: Parsed TerrainStatusFeed dict

    Returns:
        Tuple of (lifts, trails)
    """
    lifts: list[VailLift] = []
    trails: list[VailTrail] = []

    # Parse lifts
    lifts_data = data.get("Lifts", [])
    for lift_obj in lifts_data:
        if not isinstance(lift_obj, dict):
            continue

        name = lift_obj.get("Name", "")
        if not name:
            continue

        status_code = lift_obj.get("Status", 0)
        status = STATUS_MAP.get(status_code, "closed")

        # Extract additional data if available
        wait_time = lift_obj.get("WaitTime") or lift_obj.get("WaitTimeMinutes")
        lift_type = lift_obj.get("Type") or lift_obj.get("LiftType")

        lifts.append(VailLift(
            name=name,
            status=status,
            lift_type=lift_type,
            wait_time=int(wait_time) if wait_time else None,
        ))

    # Parse trails if present
    trails_data = data.get("Trails", []) or data.get("Runs", [])
    for trail_obj in trails_data:
        if not isinstance(trail_obj, dict):
            continue

        name = trail_obj.get("Name", "")
        if not name:
            continue

        status_code = trail_obj.get("Status", 0)
        status = STATUS_MAP.get(status_code, "closed")

        difficulty = trail_obj.get("Difficulty") or trail_obj.get("Rating")
        grooming = trail_obj.get("GroomingStatus") or trail_obj.get("Grooming")

        trails.append(VailTrail(
            name=name,
            status=status,
            difficulty=difficulty,
            grooming=grooming,
        ))

    return lifts, trails


def _parse_html_fallback(html: str) -> tuple[list[VailLift], list[VailTrail]]:
    """Fallback HTML parsing using BeautifulSoup.

    Some Vail resort pages may have data in a different format.
    This tries to extract lift info from visible HTML elements.

    Args:
        html: The HTML content

    Returns:
        Tuple of (lifts, trails)
    """
    soup = BeautifulSoup(html, "lxml")
    lifts: list[VailLift] = []
    trails: list[VailTrail] = []

    # Look for lift status elements (common patterns)
    # Pattern 1: Elements with data-lift-name or similar attributes
    lift_elements = soup.select("[data-lift-name], [data-name], .lift-item, .lift-status-item")

    for elem in lift_elements:
        name_attr = elem.get("data-lift-name") or elem.get("data-name")
        # Handle BeautifulSoup returning list for multi-value attributes
        if isinstance(name_attr, list):
            name = name_attr[0] if name_attr else None
        else:
            name = name_attr

        if not name:
            name_elem = elem.select_one(".lift-name, .name")
            if name_elem:
                name = name_elem.get_text(strip=True)

        if not name:
            continue

        # Try to get status
        status = "closed"
        status_elem = elem.select_one(".lift-status, .status")
        if status_elem:
            status_text = status_elem.get_text(strip=True).lower()
            if "open" in status_text:
                status = "open"
            elif "hold" in status_text:
                status = "hold"
            elif "scheduled" in status_text:
                status = "scheduled"

        lifts.append(VailLift(name=str(name), status=status))

    return lifts, trails


async def _fetch_with_curl(url: str) -> str | None:
    """Fetch URL using curl to bypass TLS fingerprinting.

    Args:
        url: URL to fetch

    Returns:
        HTML content or None if fetch fails
    """
    log = logger.bind(adapter="vail")

    # Use Liftie's user agent - Vail/Akamai whitelists known bots
    # See: https://github.com/pirxpilot/liftie
    cmd = [
        "curl", "-s", "-L",
        "-A", "Mozilla/5.0 (compatible; Liftie/1.0; +https://liftie.info)",
        "-H", "Accept: */*",
        url,
    ]

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            log.error("curl_error", returncode=result.returncode, stderr=result.stderr.decode())
            return None

        return result.stdout.decode("utf-8", errors="ignore")

    except subprocess.TimeoutExpired:
        log.error("curl_timeout")
        return None
    except Exception as e:
        log.error("fetch_error", error=str(e))
        return None


def _extract_waiting_room_redirect(html: str) -> str | None:
    """Check if page contains a waiting room redirect.

    Vail uses waitingroom.snow.com for traffic management.
    Look for: document.location.href = '/?c=vailresorts...'

    Args:
        html: HTML content

    Returns:
        Redirect URL if found, None otherwise
    """
    # Pattern from Liftie: document.location.href = '/?c=vailresorts...'
    match = re.search(r"document\.location\.href\s*=\s*'(/\?c=vailresorts[^']*)'", html)
    if match:
        return f"https://waitingroom.snow.com{match.group(1)}"
    return None


def _is_blocked_response(html: str) -> bool:
    """Check if response is Akamai/Vail block page.

    Vail uses Akamai which may block certain IPs or rate limit.
    The block page contains "system cannot process your request".

    Args:
        html: Response content

    Returns:
        True if this is a block page
    """
    return "system cannot process your request" in html.lower() or "reservations.snow.com" in html


async def fetch_vail_status(resort_url: str) -> VailData | None:
    """Fetch live status data from a Vail Resorts property.

    This is the HTTP-only execution path - NO browser automation.
    Uses curl subprocess to bypass Cloudflare/Akamai TLS fingerprinting.

    Args:
        resort_url: The URL to the terrain-and-lift-status.aspx page

    Returns:
        VailData with extracted lifts and trails, or None if fetch fails
    """
    log = logger.bind(adapter="vail", url=resort_url[:50])

    log.debug("fetching_page_with_curl")
    html = await _fetch_with_curl(resort_url)

    if not html:
        log.warning("empty_response")
        return None

    # Check if we're being blocked by Akamai
    if _is_blocked_response(html):
        log.warning("akamai_block_detected", hint="IP may be rate limited or blocked")
        return None

    # Check for waiting room redirect (from Liftie pattern)
    waiting_room_url = _extract_waiting_room_redirect(html)
    if waiting_room_url:
        log.debug("following_waiting_room_redirect", redirect_url=waiting_room_url)
        html = await _fetch_with_curl(waiting_room_url)
        if not html:
            log.warning("waiting_room_fetch_failed")
            return None

    # Try to extract TerrainStatusFeed
    terrain_data = _extract_terrain_status_feed(html)

    if terrain_data:
        lifts, trails = _parse_terrain_data(terrain_data)
        log.info(
            "fetch_complete",
            lift_count=len(lifts),
            trail_count=len(trails),
            method="terrain_status_feed",
        )
        return VailData(lifts=lifts, trails=trails)

    # Fallback to HTML parsing
    log.debug("terrain_status_feed_not_found_trying_html_fallback")
    lifts, trails = _parse_html_fallback(html)

    if lifts or trails:
        log.info(
            "fetch_complete",
            lift_count=len(lifts),
            trail_count=len(trails),
            method="html_fallback",
        )
        return VailData(lifts=lifts, trails=trails)

    log.warning("no_data_extracted")
    return None


# Convenience function for Breckenridge
async def fetch_breckenridge() -> VailData | None:
    """Fetch Breckenridge lift/trail status."""
    return await fetch_vail_status(
        "https://www.breckenridge.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"
    )
