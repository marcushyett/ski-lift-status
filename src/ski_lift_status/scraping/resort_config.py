"""
Resort configuration for HTTP-based data fetching.

This module defines the configuration structure for fetching resort status
data using simple HTTP requests. NO browser automation should be used here.

The config stores direct API endpoints that can be fetched with httpx,
along with the extraction method and selectors needed to parse the response.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils import get_data_dir


@dataclass
class ResortConfig:
    """Configuration for fetching resort status via HTTP.

    This config is designed to be executed with simple HTTP requests only.
    No browser automation, no JavaScript rendering.
    """

    resort_id: str
    resort_name: str
    platform: str  # "lumiplan", "skiplan", etc.

    # Direct API endpoints - these should be fetchable with simple HTTP GET
    # NOT status page URLs that require JavaScript
    api_endpoints: list[str] = field(default_factory=list)

    # Optional headers needed for API requests
    headers: dict[str, str] = field(default_factory=dict)

    # Platform-specific configuration
    # For lumiplan: {"map_uuid": "..."}
    # For skiplan: {"resort_slug": "..."}
    platform_config: dict[str, Any] = field(default_factory=dict)

    # Metadata
    last_validated: str | None = None
    validation_status: str | None = None  # "passing", "failing", "unknown"


# Known resort configurations with direct API endpoints
# These are discovered once via browser, then stored here for HTTP-only execution
RESORT_CONFIGS: dict[str, ResortConfig] = {
    # Les Trois Vallées - Lumiplan platform
    "68b126bc3175516c9263aed7635d14e37ff360dc": ResortConfig(
        resort_id="68b126bc3175516c9263aed7635d14e37ff360dc",
        resort_name="Les Trois Vallées",
        platform="lumiplan",
        api_endpoints=[
            "https://lumiplay.link/interactive-map-services/public/map/bd632c91-6957-494d-95a8-6a72eb87e341/dynamicPoiData",
            "https://lumiplay.link/interactive-map-services/public/map/bd632c91-6957-494d-95a8-6a72eb87e341/staticPoiData",
        ],
        platform_config={
            "map_uuid": "bd632c91-6957-494d-95a8-6a72eb87e341",
        },
    ),

    # La Plagne (Paradiski) - Skiplan platform
    "f47f7e05cc676b25b6a00f77f0b86a897f03018c": ResortConfig(
        resort_id="f47f7e05cc676b25b6a00f77f0b86a897f03018c",
        resort_name="La Plagne",
        platform="skiplan",
        api_endpoints=[
            "https://live.skiplan.com/moduleweb/2.0/php/getOuvertures.php?resort=paradiski_hiver",
        ],
        platform_config={
            "resort_slug": "paradiski_hiver",
        },
    ),

    # Zermatt-Cervinia - Nuxt.js platform
    "438e8330317f2f5a597b60acb0c0a11901b9329f": ResortConfig(
        resort_id="438e8330317f2f5a597b60acb0c0a11901b9329f",
        resort_name="Zermatt-Cervinia",
        platform="nuxtjs",
        api_endpoints=[
            "https://www.cervinia.it/en/impianti",
        ],
        platform_config={
            "page_url": "https://www.cervinia.it/en/impianti",
        },
    ),

    # Chamonix (Brévent/Flégère) - Skiplan platform
    # Discovered from: https://www.seechamonix.com/lifts/status -> iframe to live.skiplan.com
    "8432e3c536835ef8a690f63b62060a7993bfd964": ResortConfig(
        resort_id="8432e3c536835ef8a690f63b62060a7993bfd964",
        resort_name="Chamonix (Brévent/Flégère)",
        platform="skiplan",
        api_endpoints=[
            "https://live.skiplan.com/moduleweb/2.0/php/getOuvertures.php?resort=chamonix_hiver_general",
        ],
        platform_config={
            "resort_slug": "chamonix_hiver_general",
        },
    ),

    # Breckenridge - Vail Resorts platform
    # TerrainStatusFeed JavaScript object embedded in HTML
    "c329b1fe669c197d615896dfd4e38d4bb039e30c": ResortConfig(
        resort_id="c329b1fe669c197d615896dfd4e38d4bb039e30c",
        resort_name="Breckenridge",
        platform="vail",
        api_endpoints=[
            "https://www.breckenridge.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
        ],
        platform_config={
            "page_url": "https://www.breckenridge.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx",
        },
    ),

    # Les Gets-Morzine - Intermaps platform (Portes du Soleil)
    # Discovered from: https://www.lesgets.com/en/.../live-info-slopes/ -> intermaps.com
    "cafb6b6d5f25860a682a8b6d67efe689218618a5": ResortConfig(
        resort_id="cafb6b6d5f25860a682a8b6d67efe689218618a5",
        resort_name="Les Gets-Morzine (Portes du Soleil)",
        platform="intermaps",
        api_endpoints=[
            "https://winter.intermaps.com/portes_du_soleil/data?lang=en",
        ],
        platform_config={
            "resort_slug": "portes_du_soleil",
        },
    ),

    # TODO: Add configs for remaining resorts after finding their APIs:
    # - Cortina d'Ampezzo (9a8be208c4f1832db8bf13c7102e2dcc3eef0a84)
}


def get_resort_config(resort_id: str) -> ResortConfig | None:
    """Get the configuration for a resort by ID.

    Args:
        resort_id: The resort's unique identifier

    Returns:
        ResortConfig if found, None otherwise
    """
    return RESORT_CONFIGS.get(resort_id)


def get_all_resort_configs() -> list[ResortConfig]:
    """Get all configured resorts.

    Returns:
        List of all ResortConfig objects
    """
    return list(RESORT_CONFIGS.values())


def save_resort_config(config: ResortConfig, path: Path | None = None) -> Path:
    """Save a resort config to JSON file.

    Args:
        config: The config to save
        path: Output path. If None, uses default location.

    Returns:
        Path to the saved file.
    """
    if path is None:
        configs_dir = get_data_dir() / "resort_configs"
        configs_dir.mkdir(exist_ok=True)
        path = configs_dir / f"{config.resort_id}.json"

    data = {
        "resort_id": config.resort_id,
        "resort_name": config.resort_name,
        "platform": config.platform,
        "api_endpoints": config.api_endpoints,
        "headers": config.headers,
        "platform_config": config.platform_config,
        "last_validated": config.last_validated,
        "validation_status": config.validation_status,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return path


def load_resort_config(resort_id: str, path: Path | None = None) -> ResortConfig | None:
    """Load a resort config from JSON file.

    Args:
        resort_id: The resort ID to load config for.
        path: Path to the config file. If None, uses default location.

    Returns:
        ResortConfig if found, None otherwise.
    """
    if path is None:
        path = get_data_dir() / "resort_configs" / f"{resort_id}.json"

    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        return ResortConfig(**data)
