"""Common utility functions."""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def model_to_dict(model: Any) -> dict:
    """Convert a Pydantic model to dict, compatible with v1 and v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    elif hasattr(model, "dict"):
        return model.dict()
    else:
        raise TypeError(f"Cannot convert {type(model)} to dict")


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_data_dir() -> Path:
    """Get the data directory."""
    data_dir = get_project_root() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir

