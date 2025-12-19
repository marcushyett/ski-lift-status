#!/usr/bin/env python3
"""Batch discover status pages for ski resorts using heuristics and patterns."""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(__file__).parent.parent / "data"
STATUS_PAGES_FILE = DATA_DIR / "status_pages.csv"
DISCOVERY_RESULTS_FILE = DATA_DIR / "discovery_results.json"


# Known status page URL patterns by domain
DOMAIN_PATTERNS = {
    # See* sites (seeChamonix, seeLaPlagne, etc.)
    "seechamonix.com": {"lifts": "/lifts/status"},
    "seelaplagne.com": {"lifts": "/lifts/status"},
    "seelesarcs.com": {"lifts": "/lifts/status"},
    "seevalthorens.com": {"lifts": "/lifts/status"},
    "seetignes.com": {"lifts": "/lifts/status"},
    "seealpedhuez.com": {"lifts": "/lifts/status"},
    "seemeribel.com": {"lifts": "/lifts/status"},
    "seearc1950.com": {"lifts": "/lifts/status"},
    "seeavoriaz.com": {"lifts": "/lifts/status"},
    "seecourchevel.com": {"lifts": "/lifts/status"},

    # Dolomiti Superski
    "dolomitisuperski.com": {"lifts": "/en/live-info/lifts"},

    # Paradiski/Compagnie des Alpes
    "paradiski.com": {"lifts": "/en/useful-info/lifts-open"},

    # Swiss resorts
    "arosalenzerheide.swiss": {"lifts": "/en/Ski-Area/Lift-Company/Operating-hours-winter"},
    "zermatt.ch": {"lifts": "/en/live-info/lifts"},

    # Austrian resorts
    "skiwelt.at": {"lifts": "/en/lift-status-winter.html"},
    "saalbach.com": {"lifts": "/en/live-info/lifts-and-pistes"},
    "serfaus-fiss-ladis.at": {"lifts": "/en/winter-holiday/ski-area-status"},
    "kitzski.at": {"lifts": "/en/current-info/kitz-lift-status.html"},
    "zillertalarena.com": {"lifts": "/en/information-services/live-cams-weather/snow-report/"},
    "mayrhofen.at": {"lifts": "/en/stories/open-cable-cars-mayrhofner-bergbahnen-winter"},

    # Italian resorts
    "cervinia.it": {"lifts": "/en/impianti"},
    "altabadia.org": {"lifts": "/en/open-lifts-snow-report-dolomites"},

    # French resorts
    "les3vallees.com": {"lifts": "/fr/live/ouverture-des-pistes-et-remontees"},
    "grand-massif.com": {"lifts": "/en/information-on-trail-openings/"},
    "sybelles.ski": {"lifts": "/en/skiing-in-les-sybelles/slopes-and-lifts-open/"},
    "lesgets.com": {"lifts": "/en/discover-the-resort/ski-winter-sports/live-info-slopes/"},
    "laclusaz.com": {"lifts": "/en/ski/alpine-skiing/"},
    "serre-chevalier.com": {"lifts": "/en/schedules-mechanical-lifts"},
    "megeve.com": {"lifts": "/hiver/en/ski-area-opening-information/"},
    "les2alpes.com": {"lifts": "/en/ski/snow-front/"},

    # US resorts
    "breckenridge.com": {"lifts": "/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"},
    "vail.com": {"lifts": "/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"},
    "parkcitymountain.com": {"lifts": "/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"},
    "mammothmountain.com": {"lifts": "/on-the-mountain/mountain-information/lift-status"},

    # Australian resorts
    "perisher.com.au": {"lifts": "/conditions/lifts-and-terrain"},

    # Lumiplan bulletin sites
    "bulletin.lumiplan.pro": {"lifts": "/bulletin.php"},
}

# Common URL patterns to try for unknown domains
COMMON_PATTERNS = [
    "/en/lift-status",
    "/en/lifts-status",
    "/en/lifts",
    "/en/live-info/lifts",
    "/en/terrain-status",
    "/en/snow-report",
    "/en/conditions",
    "/en/ski-area/lifts",
    "/lift-status",
    "/lifts-status",
    "/terrain-status",
    "/conditions",
    "/snow-report",
    "/impianti",
    "/anlagen",
    "/lifte",
    "/remontees",
    "/ouverture",
]

# Platform detection patterns
PLATFORM_DETECTORS = {
    "lumiplan": [
        r"bulletin\.lumiplan\.pro",
        r"lumiplan",
    ],
    "dolomiti": [
        r"dolomitisuperski\.com",
    ],
    "vail": [
        r"breckenridge\.com",
        r"vail\.com",
        r"parkcitymountain\.com",
        r"keystone\.com",
        r"heavenly\.com",
    ],
    "infosnow": [
        r"infosnow\.ch",
        r"apgsga",
    ],
    "nuxt": [
        r"cervinia\.it",
    ],
}


def detect_platform(url: str) -> str:
    """Detect the platform/technology used by a URL."""
    for platform, patterns in PLATFORM_DETECTORS.items():
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return platform
    return "custom"


def normalize_domain(url: str) -> str:
    """Extract and normalize domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def get_lift_names_for_resort(resort_id: str, lifts_csv: Path) -> list[str]:
    """Get lift names for a resort."""
    names = []
    with open(lifts_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if resort_id in row.get("ski_area_ids", ""):
                name = row.get("name", "").strip()
                if name:
                    names.append(name)
    return names


def discover_status_page(resort: dict) -> dict:
    """Discover status page URL for a resort using heuristics."""
    result = {
        "resort_id": resort["id"],
        "resort_name": resort["name"],
        "website_url": "",
        "status_page_url": "",
        "platform": "",
        "confidence": 0.0,
        "method": "",
    }

    websites = resort.get("websites", "")
    if not websites:
        result["method"] = "no_website"
        return result

    # Try first website
    website = websites.split(";")[0].strip()
    if not website.startswith("http"):
        website = f"https://{website}"

    result["website_url"] = website
    domain = normalize_domain(website)

    # Check if we have a known pattern for this domain
    for known_domain, patterns in DOMAIN_PATTERNS.items():
        if known_domain in domain or domain in known_domain:
            status_path = patterns.get("lifts", "")
            if status_path:
                result["status_page_url"] = f"https://{known_domain}{status_path}"
                result["platform"] = detect_platform(result["status_page_url"])
                result["confidence"] = 0.85
                result["method"] = "known_domain"
                return result

    # Try common patterns
    for pattern in COMMON_PATTERNS[:5]:  # Only try first 5 patterns
        candidate = f"{website.rstrip('/')}{pattern}"
        result["status_page_url"] = candidate
        result["platform"] = detect_platform(candidate)
        result["confidence"] = 0.3
        result["method"] = "common_pattern"
        return result

    result["method"] = "unknown"
    return result


def load_existing_status_pages() -> dict[str, dict]:
    """Load existing status pages CSV."""
    existing = {}
    if STATUS_PAGES_FILE.exists():
        with open(STATUS_PAGES_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing[row["resort_id"]] = row
    return existing


def get_top_resorts(n: int = 500) -> list[dict]:
    """Get top N resorts by lift count."""
    lifts_csv = DATA_DIR / "lifts.csv"
    resorts_csv = DATA_DIR / "resorts.csv"

    # Count lifts per resort
    lift_counts = defaultdict(int)
    with open(lifts_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for ski_id in row.get("ski_area_ids", "").split(";"):
                ski_id = ski_id.strip()
                if ski_id:
                    lift_counts[ski_id] += 1

    # Get resort info
    resorts = []
    with open(resorts_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            resort_id = row.get("id", "")
            if resort_id and resort_id in lift_counts:
                resorts.append({
                    "id": resort_id,
                    "name": row.get("name", ""),
                    "websites": row.get("websites", ""),
                    "lift_count": lift_counts[resort_id],
                })

    # Sort by lift count
    resorts.sort(key=lambda x: x["lift_count"], reverse=True)
    return resorts[:n]


def save_status_pages(entries: list[dict]) -> None:
    """Save status pages to CSV."""
    fieldnames = ["resort_id", "resort_name", "website_url", "status_page_url"]

    with open(STATUS_PAGES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow({
                "resort_id": entry.get("resort_id", ""),
                "resort_name": entry.get("resort_name", ""),
                "website_url": entry.get("website_url", ""),
                "status_page_url": entry.get("status_page_url", ""),
            })


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch discover status pages")
    parser.add_argument("--top", type=int, default=500, help="Number of top resorts")
    parser.add_argument("--override", action="store_true", help="Override existing entries")
    parser.add_argument("--output", type=str, help="Output JSON file")
    args = parser.parse_args()

    print(f"Loading top {args.top} resorts by lift count...")
    resorts = get_top_resorts(args.top)
    print(f"Found {len(resorts)} resorts")

    existing = load_existing_status_pages()
    print(f"Existing status pages: {len(existing)}")

    # Discover for all resorts
    results = []
    for i, resort in enumerate(resorts):
        if not args.override and resort["id"] in existing:
            # Keep existing entry
            result = {
                "resort_id": resort["id"],
                "resort_name": resort["name"],
                "website_url": existing[resort["id"]].get("website_url", ""),
                "status_page_url": existing[resort["id"]].get("status_page_url", ""),
                "confidence": 1.0,
                "method": "existing",
            }
        else:
            result = discover_status_page(resort)

        results.append(result)

        if (i + 1) % 50 == 0:
            print(f"Processed {i + 1}/{len(resorts)} resorts...")

    # Count results by method
    method_counts = defaultdict(int)
    for r in results:
        method_counts[r.get("method", "unknown")] += 1

    print(f"\nDiscovery results by method:")
    for method, count in sorted(method_counts.items()):
        print(f"  {method}: {count}")

    # Save results
    all_entries = []
    for result in results:
        if result.get("status_page_url"):
            all_entries.append(result)

    all_entries.sort(key=lambda x: x["resort_name"])
    save_status_pages(all_entries)
    print(f"\nSaved {len(all_entries)} entries to status_pages.csv")

    # Output JSON if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump({
                "total": len(results),
                "with_status_page": len(all_entries),
                "results": results,
            }, f, indent=2)
        print(f"Saved detailed results to {args.output}")

    return results


if __name__ == "__main__":
    main()
