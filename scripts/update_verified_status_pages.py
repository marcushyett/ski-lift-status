#!/usr/bin/env python3
"""Update status_pages.csv with verified URLs from WebSearch."""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
STATUS_PAGES_FILE = DATA_DIR / "status_pages.csv"

# Verified status page URLs from WebSearch (December 2025)
VERIFIED_URLS = {
    # SkiStar resorts
    "Åre": {
        "url": "https://www.skistar.com/en/ski-destinations/are/winter-in-are/weather-and-slopes/",
        "platform": "skistar",
    },
    "Trysil": {
        "url": "https://www.skistar.com/en/ski-destinations/trysil/winter-in-trysil/weather-and-slopes/",
        "platform": "skistar",
    },
    "Lindvallen": {
        "url": "https://www.skistar.com/en/ski-destinations/salen/winter-in-salen/weather-and-slopes/",
        "platform": "skistar",
    },

    # Austrian resorts
    "Silvretta Arena Ischgl/Samnaun": {
        "url": "https://www.ischgl.com/en/winter/silvretta-arena/open-faciliites",
        "platform": "ischgl",
    },
    "Sölden": {
        "url": "https://www.soelden.com/en/live-information/status",
        "platform": "soelden",
    },
    "Lech/Zürs": {
        "url": "https://www.skiarlberg.at/en/lech-zuers/live-info/cable-cars-lifts",
        "platform": "skiarlberg",
    },
    "St. Anton/St. Christoph/Stuben": {
        "url": "https://www.skiarlberg.at/en/st-anton/live-info/cable-cars-lifts",
        "platform": "skiarlberg",
    },
    "Silvretta Montafon": {
        "url": "https://www.silvretta-montafon.at/en/live",
        "platform": "custom",
    },
    "Hochzillertal-Hochfügen": {
        "url": "https://www.hochzillertal.com/en/live",
        "platform": "custom",
    },

    # Swiss resorts
    "Corviglia": {
        "url": "https://www.stmoritz.com/en/live/cable-cars-slopes",
        "platform": "stmoritz",
    },
    "Laax": {
        "url": "https://live.laax.com/en/lifts",
        "platform": "laax",
    },
    "Aletsch Arena": {
        "url": "https://www.aletscharena.ch/en/live-info",
        "platform": "custom",
    },
    "Parsenn": {
        "url": "https://www.davos.ch/en/winter/live-info",
        "platform": "custom",
    },

    # French resorts
    "Les Deux Alpes": {
        "url": "https://www.see2alpes.com/lifts/status",
        "platform": "seelift",
    },
    "Avoriaz": {
        "url": "https://www.seeavoriaz.com/lifts/status",
        "platform": "seelift",
    },
    "Val Cenis": {
        "url": "https://www.valcenis.com/en/live-info",
        "platform": "custom",
    },
    "Espace Lumière": {
        "url": "https://www.praloup.com/en/live-info",
        "platform": "custom",
    },
    "Forêt Blanche : Vars/Risoul": {
        "url": "https://www.vars.com/en/live-info",
        "platform": "custom",
    },

    # Italian resorts
    "Livigno": {
        "url": "https://www.livigno.eu/en/lifts",
        "platform": "livigno",
    },
    "Monterosa Ski": {
        "url": "https://www.monterosa-ski.com/en/live-info",
        "platform": "custom",
    },

    # US resorts
    "Park City Mountain Resort": {
        "url": "https://www.parkcitymountain.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
        "platform": "vail",
    },
    "Deer Valley Resort": {
        "url": "https://www.deervalley.com/explore-the-mountain/mountain-report",
        "platform": "deervalley",
    },
    "Big Sky Resort": {
        "url": "https://bigskyresort.com/the-mountain/conditions",
        "platform": "custom",
    },

    # Australian resorts
    "Perisher": {
        "url": "https://www.perisher.com.au/conditions/lifts-and-terrain",
        "platform": "perisher",
    },

    # Spanish resorts
    "Estació d'Esquí Baqueira-Beret": {
        "url": "https://www.baqueira.es/estado-pistas",
        "platform": "baqueira",
    },

    # Norwegian resorts
    "Branäs": {
        "url": "https://www.branas.se/weather-and-slopes/",
        "platform": "custom",
    },
}


def update_status_pages():
    """Update status_pages.csv with verified URLs."""
    # Load existing entries
    entries = {}
    if STATUS_PAGES_FILE.exists():
        with open(STATUS_PAGES_FILE, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries[row["resort_name"]] = row

    print(f"Loaded {len(entries)} existing entries")

    # Update with verified URLs
    updated_count = 0
    for resort_name, info in VERIFIED_URLS.items():
        if resort_name in entries:
            old_url = entries[resort_name].get("status_page_url", "")
            new_url = info["url"]
            if old_url != new_url:
                entries[resort_name]["status_page_url"] = new_url
                updated_count += 1
                print(f"Updated: {resort_name}")
                print(f"  Old: {old_url}")
                print(f"  New: {new_url}")
        else:
            # Find by partial match
            for name, entry in entries.items():
                if resort_name.lower() in name.lower() or name.lower() in resort_name.lower():
                    old_url = entry.get("status_page_url", "")
                    new_url = info["url"]
                    if old_url != new_url:
                        entry["status_page_url"] = new_url
                        updated_count += 1
                        print(f"Updated (partial match): {name}")
                        print(f"  Old: {old_url}")
                        print(f"  New: {new_url}")
                    break

    # Save updated entries
    fieldnames = ["resort_id", "resort_name", "website_url", "status_page_url"]
    sorted_entries = sorted(entries.values(), key=lambda x: x.get("resort_name", ""))

    with open(STATUS_PAGES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in sorted_entries:
            writer.writerow({
                "resort_id": entry.get("resort_id", ""),
                "resort_name": entry.get("resort_name", ""),
                "website_url": entry.get("website_url", ""),
                "status_page_url": entry.get("status_page_url", ""),
            })

    print(f"\nUpdated {updated_count} entries")
    print(f"Total entries: {len(sorted_entries)}")


if __name__ == "__main__":
    update_status_pages()
