"""Status page discovery module for finding resort lift status pages."""

from .agent import (
    DiscoveryAgent,
    DiscoveryResult,
    run_discovery_for_resort,
    run_discovery_for_resorts,
)
from .serper import SerperClient

__all__ = [
    "DiscoveryAgent",
    "DiscoveryResult",
    "SerperClient",
    "run_discovery_for_resort",
    "run_discovery_for_resorts",
]
