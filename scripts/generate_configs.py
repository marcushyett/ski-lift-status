#!/usr/bin/env python3
"""Generate resort configs from discovered status pages."""

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIGS_DIR = Path(__file__).parent.parent / "src" / "ski_lift_status" / "configs"
STATUS_PAGES_FILE = DATA_DIR / "status_pages.csv"
RESORTS_JSON = CONFIGS_DIR / "resorts.json"

# Platform detection patterns (URL -> platform)
PLATFORM_PATTERNS = [
    # See* sites (unified lift status interface)
    (r"see[a-z]+\.com/lifts/status", "seelift"),
    (r"see[a-z]+\.com", "seelift"),

    # Lumiplan bulletin
    (r"bulletin\.lumiplan\.pro", "lumiplan"),

    # Dolomiti Superski
    (r"dolomitisuperski\.com", "dolomiti"),

    # Vail Resorts (Epic Pass)
    (r"(breckenridge|vail|parkcitymountain|keystone|heavenly|northstar|beaver|kirkwood)\.com.*terrain.*lift.*status", "vail"),
    (r"epicmix|EpicMix", "vail"),

    # SkiStar resorts
    (r"skistar\.com.*weather.*slopes", "skistar"),

    # Ski Arlberg (Lech, Zürs, St. Anton)
    (r"skiarlberg\.at", "skiarlberg"),

    # Swiss resorts
    (r"stmoritz\.com.*live", "stmoritz"),
    (r"live\.laax\.com", "laax"),
    (r"arosalenzerheide\.swiss", "arosalenzerheide"),

    # Austrian resorts
    (r"ischgl\.com.*open.*facili", "ischgl"),
    (r"soelden\.com.*status", "soelden"),
    (r"skiwelt\.at.*lift.*status", "skiwelt"),
    (r"saalbach\.com.*live.*info", "saalbach"),
    (r"serfaus-fiss-ladis\.at", "serfaus"),
    (r"kitzski\.at.*lift.*status", "kitzski"),
    (r"zillertalarena\.com", "zillertal"),

    # Italian resorts
    (r"cervinia\.it.*impianti", "nuxt"),
    (r"livigno\.eu.*lifts", "livigno"),

    # Spanish resorts
    (r"baqueira\.es.*estado", "baqueira"),

    # French resorts (Lumiplan based)
    (r"les3vallees\.com", "lumiplan"),
    (r"grand-massif\.com", "lumiplan"),
    (r"sybelles\.ski", "lumiplan"),
    (r"laclusaz\.com", "lumiplan"),
    (r"megeve\.com", "lumiplan"),
    (r"serre-chevalier\.com", "lumiplan"),

    # Perisher (Australia)
    (r"perisher\.com\.au.*lifts", "perisher"),

    # Deer Valley
    (r"deervalley\.com.*mountain.*report", "deervalley"),

    # Big Sky
    (r"bigskyresort\.com", "bigsky"),

    # Default to custom
    (r".*", "custom"),
]


def detect_platform(url: str) -> str:
    """Detect the platform from a URL."""
    url_lower = url.lower()
    for pattern, platform in PLATFORM_PATTERNS:
        if re.search(pattern, url_lower):
            return platform
    return "custom"


def fix_url(url: str, website_url: str = "") -> str:
    """Fix malformed URLs with incorrect path appended."""
    # Check for common malformed patterns
    if "/en/lift-status" in url and not any(good in url for good in [
        "see", "skistar", "skiarlberg", "dolomiti", "lumiplan",
        "skiwelt", "saalbach", "kitzski", "soelden", "ischgl"
    ]):
        # Remove the incorrect suffix
        url = re.sub(r"/en/lift-status.*$", "", url)

    # Fix URLs with multiple URLs concatenated (space separated)
    if " " in url:
        parts = url.split()
        # Take the first valid URL
        for part in parts:
            if part.startswith("http"):
                url = part
                break

    # Ensure URL has protocol
    if url and not url.startswith("http"):
        url = f"https://{url}"

    return url


def url_to_slug(name: str) -> str:
    """Convert resort name to URL-friendly slug."""
    # Remove special characters
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    # Replace spaces with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:50]


def load_status_pages() -> list[dict]:
    """Load status pages from CSV."""
    pages = []
    if STATUS_PAGES_FILE.exists():
        with open(STATUS_PAGES_FILE, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status_page_url"):
                    pages.append(row)
    return pages


def load_existing_configs() -> dict:
    """Load existing configs from resorts.json."""
    if RESORTS_JSON.exists():
        with open(RESORTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0", "resorts": []}


def generate_config(page: dict) -> dict:
    """Generate a resort config from a status page entry."""
    raw_url = page.get("status_page_url", "")
    website_url = page.get("website_url", "")

    # Fix malformed URLs
    url = fix_url(raw_url, website_url)
    platform = detect_platform(url)

    config = {
        "id": url_to_slug(page.get("resort_name", "")),
        "name": page.get("resort_name", ""),
        "openskimap_id": page.get("resort_id", ""),
        "platform": platform,
        "url": url,
    }

    # Add dataUrl for platforms that need it
    if platform == "lumiplan":
        # Try to extract station name from URL
        parsed = urlparse(url)
        if "bulletin.lumiplan.pro" in parsed.netloc:
            config["dataUrl"] = url
        else:
            # Construct Lumiplan URL based on resort name
            station = url_to_slug(page.get("resort_name", "")).replace("-", "")
            config["dataUrl"] = f"https://bulletin.lumiplan.pro/bulletin.php?station={station}&region=alpes&pays=france&lang=en"

    # Add website URL if available
    if page.get("website_url"):
        config["website"] = page.get("website_url")

    return config


def generate_all_configs():
    """Generate configs for all status pages."""
    pages = load_status_pages()
    print(f"Loaded {len(pages)} status pages")

    existing = load_existing_configs()
    existing_ids = {r.get("openskimap_id") for r in existing.get("resorts", [])}
    print(f"Existing configs: {len(existing_ids)}")

    # Generate new configs
    new_configs = []
    platform_counts = {}

    for page in pages:
        resort_id = page.get("resort_id", "")
        if resort_id in existing_ids:
            continue

        config = generate_config(page)
        new_configs.append(config)

        platform = config.get("platform", "custom")
        platform_counts[platform] = platform_counts.get(platform, 0) + 1

    print(f"\nGenerated {len(new_configs)} new configs")
    print("\nPlatform distribution:")
    for platform, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        print(f"  {platform}: {count}")

    # Merge with existing configs
    all_resorts = existing.get("resorts", []) + new_configs

    # Update metadata
    output = {
        "version": "1.0",
        "updated": "2025-12-19",
        "total_resorts": len(all_resorts),
        "platforms": dict(sorted(platform_counts.items(), key=lambda x: -x[1])),
        "resorts": sorted(all_resorts, key=lambda x: x.get("name", "")),
    }

    # Save to resorts.json
    with open(RESORTS_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_resorts)} configs to {RESORTS_JSON}")

    # Print sample configs
    print("\nSample new configs:")
    for config in new_configs[:5]:
        print(f"  - {config['name']} ({config['platform']})")
        print(f"    URL: {config['url']}")


if __name__ == "__main__":
    generate_all_configs()
