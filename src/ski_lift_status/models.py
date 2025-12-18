"""Data models for ski lift status."""

from pydantic import BaseModel


class Resort(BaseModel):
    """Ski resort/area model."""

    id: str
    name: str
    countries: str
    status: str
    regions: str | None = None
    websites: str | None = None


class Lift(BaseModel):
    """Ski lift model."""

    id: str
    name: str | None = None
    lift_type: str | None = None
    status: str | None = None
    countries: str | None = None
    regions: str | None = None
    localities: str | None = None
    ski_area_names: str | None = None
    ski_area_ids: str | None = None


class Run(BaseModel):
    """Ski run model."""

    id: str
    name: str | None = None
    run_type: str | None = None
    difficulty: str | None = None
    status: str | None = None
    countries: str | None = None
    regions: str | None = None
    localities: str | None = None
    ski_area_names: str | None = None
    ski_area_ids: str | None = None

