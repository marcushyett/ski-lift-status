"""Ski Lift Status - A library for fetching ski resort data from OpenSkiMap."""

from .data_fetcher import (
    fetch_and_save_all_data,
    get_lifts_for_resort,
    get_resort_by_id,
    get_runs_for_resort,
    load_lifts,
    load_resorts,
    load_runs,
)
from .models import Lift, Resort, Run

__version__ = "0.1.0"

__all__ = [
    "fetch_and_save_all_data",
    "get_lifts_for_resort",
    "get_resort_by_id",
    "get_runs_for_resort",
    "load_lifts",
    "load_resorts",
    "load_runs",
    "Lift",
    "Resort",
    "Run",
]
