"""
Dolomiti Superski platform adapter.

Dolomiti Superski is a consortium of 12 ski regions in the Dolomites, Italy.
Their website provides lift status information via server-rendered HTML tables.

Known resorts using Dolomiti Superski:
- Cortina d'Ampezzo
- Alta Badia
- Val Gardena
- Kronplatz
- And others in the Dolomites

URL pattern:
- https://www.dolomitisuperski.com/{lang}/live-info/lifts/{resort-slug}

Extraction approach:
1. Fetch the HTML page (using curl to bypass Cloudflare TLS fingerprinting)
2. Parse lift data from <table class="itemsTableList"> elements
3. Row class "tr-open-item" = open, "tr-close-item" = closed
4. Extract lift name from <p class="title">
5. Extract lift type from <p class="type-lift">
"""

import asyncio
import subprocess
from dataclasses import dataclass

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)


@dataclass
class DolomitisuperskiLift:
    """Lift data from Dolomiti Superski."""
    name: str
    status: str | None
    lift_type: str | None = None
    number: str | None = None
    season_start: str | None = None
    season_end: str | None = None
    opening_hours: str | None = None


@dataclass
class DolomitisuperskiTrail:
    """Trail data from Dolomiti Superski."""
    name: str
    status: str | None
    difficulty: str | None = None
    number: str | None = None


@dataclass
class DolomitisuperskiData:
    """Extracted data from Dolomiti Superski."""
    lifts: list[DolomitisuperskiLift]
    trails: list[DolomitisuperskiTrail]
    resort_slug: str | None = None


def _parse_lift_tables(soup: BeautifulSoup) -> list[DolomitisuperskiLift]:
    """Parse lift data from HTML tables.

    The structure is:
    <table class="table itemsTableList">
        <tbody>
            <tr class="tr-open-item"> or <tr class="tr-close-item">
                <td><span class="nr">1</span></td>
                <td><p class="title">Lift Name</p></td>
                <td><p class="type-lift">Chairlift 4</p></td>
                <td><p class="status">Open/Closed</p></td>
                ...
            </tr>
        </tbody>
    </table>

    Args:
        soup: BeautifulSoup parsed HTML

    Returns:
        List of parsed lifts
    """
    lifts: list[DolomitisuperskiLift] = []
    seen_names: set[str] = set()

    # Find all lift table rows
    rows = soup.select("table.itemsTableList tbody tr")

    for row in rows:
        # Determine status from row class
        row_classes = row.get("class", [])
        if "tr-open-item" in row_classes:
            status = "open"
        elif "tr-close-item" in row_classes:
            status = "closed"
        else:
            continue  # Not a lift row

        # Get lift name from <p class="title">
        title_elem = row.select_one("p.title")
        if not title_elem:
            continue

        name = title_elem.get_text(strip=True)
        if not name:
            continue

        # Deduplicate by name (same lift appears in multiple tables)
        if name in seen_names:
            continue
        seen_names.add(name)

        # Get lift number from <span class="nr">
        nr_elem = row.select_one("span.nr")
        number = nr_elem.get_text(strip=True) if nr_elem else None

        # Get lift type from <p class="type-lift">
        type_elem = row.select_one("p.type-lift")
        lift_type = None
        if type_elem:
            # Remove icon, get just text
            lift_type = type_elem.get_text(strip=True)

        # Get season dates if available
        season_elem = row.select_one("p.season")
        season_start = None
        season_end = None
        if season_elem:
            time_elems = season_elem.select("time")
            if len(time_elems) >= 1:
                season_start = time_elems[0].get("datetime")
            if len(time_elems) >= 2:
                season_end = time_elems[1].get("datetime")

        # Get opening hours
        hours_cells = row.select("td")
        opening_hours = None
        for cell in hours_cells:
            text = cell.get_text(strip=True)
            if ":" in text and "-" not in text[:5]:
                # Looks like time format (e.g., "09:00 - 16:30")
                if "08:" in text or "09:" in text or "10:" in text:
                    opening_hours = text
                    break

        lifts.append(DolomitisuperskiLift(
            name=name,
            status=status,
            lift_type=lift_type,
            number=number,
            season_start=season_start,
            season_end=season_end,
            opening_hours=opening_hours,
        ))

    return lifts


def _parse_trail_tables(soup: BeautifulSoup) -> list[DolomitisuperskiTrail]:
    """Parse trail data from HTML tables.

    Similar structure to lifts but on the slopes page.

    Args:
        soup: BeautifulSoup parsed HTML

    Returns:
        List of parsed trails
    """
    # Trails use same structure as lifts
    # This function can be expanded if needed for slopes pages
    return []


async def fetch_dolomitisuperski_status(
    resort_slug: str,
    resource_type: str = "lifts",
    lang: str = "en"
) -> DolomitisuperskiData | None:
    """Fetch live status data from Dolomiti Superski.

    This is the HTTP-only execution path - NO browser automation.
    Uses curl subprocess to bypass Cloudflare TLS fingerprinting.

    Args:
        resort_slug: The resort slug (e.g., "cortina-d-ampezzo")
        resource_type: Either "lifts" or "open-slopes"
        lang: Language code (default "en")

    Returns:
        DolomitisuperskiData with extracted lifts and trails, or None if fetch fails
    """
    log = logger.bind(adapter="dolomitisuperski", resort_slug=resort_slug)

    url = f"https://www.dolomitisuperski.com/{lang}/live-info/{resource_type}/{resort_slug}"

    try:
        # Use curl to bypass Cloudflare TLS fingerprinting
        # httpx gets blocked with 403 but curl works
        log.debug("fetching_page_with_curl", url=url)

        cmd = [
            "curl", "-s", "-L",
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-H", "Accept-Language: en-US,en;q=0.9",
            url,
        ]

        # Run curl in a subprocess
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            log.error("curl_error", returncode=result.returncode, stderr=result.stderr.decode())
            return None

        html = result.stdout.decode("utf-8", errors="ignore")

    except subprocess.TimeoutExpired:
        log.error("curl_timeout")
        return None
    except Exception as e:
        log.error("fetch_error", error=str(e))
        return None

    if not html:
        log.warning("empty_response")
        return None

    soup = BeautifulSoup(html, "lxml")

    lifts = _parse_lift_tables(soup)
    trails = _parse_trail_tables(soup)

    log.info(
        "fetch_complete",
        lift_count=len(lifts),
        trail_count=len(trails),
    )

    return DolomitisuperskiData(lifts=lifts, trails=trails, resort_slug=resort_slug)


# Adapter interface functions for compatibility with other adapters


def detect(resources: list) -> bool:
    """Detect if resources are from Dolomiti Superski platform.

    Args:
        resources: List of captured resources

    Returns:
        True if any resource matches Dolomiti Superski patterns
    """
    for resource in resources:
        url = getattr(resource, "url", str(resource))
        if "dolomitisuperski.com" in url:
            return True
    return False


def extract(resources: list) -> DolomitisuperskiData | None:
    """Extract data from captured resources.

    Note: This is a sync fallback - prefer using fetch_dolomitisuperski_status
    for async HTTP fetching.

    Args:
        resources: List of captured resources

    Returns:
        Extracted data or None
    """
    for resource in resources:
        content = getattr(resource, "content", None) or getattr(resource, "body", None)
        if not content:
            continue

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")

        if "itemsTableList" in content:
            soup = BeautifulSoup(content, "lxml")
            lifts = _parse_lift_tables(soup)
            trails = _parse_trail_tables(soup)

            if lifts:
                return DolomitisuperskiData(lifts=lifts, trails=trails)

    return None


def get_status_summary(data: DolomitisuperskiData | None) -> dict[str, dict[str, int]] | None:
    """Get aggregate status counts from extracted data.

    Args:
        data: Extracted Dolomiti Superski data

    Returns:
        Dict with 'lifts' and 'trails' status counts
    """
    if not data:
        return None

    lift_counts: dict[str, int] = {}
    for lift in data.lifts:
        status = lift.status or "unknown"
        lift_counts[status] = lift_counts.get(status, 0) + 1

    trail_counts: dict[str, int] = {}
    for trail in data.trails:
        status = trail.status or "unknown"
        trail_counts[status] = trail_counts.get(status, 0) + 1

    return {
        "lifts": lift_counts,
        "trails": trail_counts,
    }
