"""Logging configuration for the scraping pipeline."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

# Check if debug mode is enabled
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")


def get_debug_dir() -> Path:
    """Get the debug output directory."""
    debug_dir = Path(__file__).parent.parent.parent.parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    return debug_dir


def save_debug_artifact(
    name: str,
    data: Any,
    resort_id: str | None = None,
    phase: str | None = None,
) -> Path | None:
    """Save a debug artifact to disk.

    Args:
        name: Name of the artifact.
        data: Data to save (will be JSON serialized).
        resort_id: Optional resort ID for organization.
        phase: Optional phase name for organization.

    Returns:
        Path to saved file, or None if debug mode is disabled.
    """
    if not DEBUG:
        return None

    debug_dir = get_debug_dir()

    # Create subdirectory structure
    if resort_id:
        debug_dir = debug_dir / resort_id
        debug_dir.mkdir(exist_ok=True)

    if phase:
        debug_dir = debug_dir / phase
        debug_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{name}.json"
    filepath = debug_dir / filename

    # Serialize and save
    try:
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        elif hasattr(data, "__dict__"):
            data = data.__dict__

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return filepath
    except Exception as e:
        structlog.get_logger().warning("failed_to_save_debug_artifact", error=str(e))
        return None


def configure_logging() -> None:
    """Configure structured logging for the application."""
    # Determine log level
    level_map = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
    }
    level = level_map.get(LOG_LEVEL.upper(), 20)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True)
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.BoundLogger:
    """Get a logger instance with optional initial context.

    Args:
        name: Optional logger name.
        **initial_context: Initial context to bind to the logger.

    Returns:
        Configured logger instance.
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


# LangSmith integration
def setup_langsmith() -> bool:
    """Set up LangSmith tracing if configured.

    Returns:
        True if LangSmith is enabled, False otherwise.
    """
    api_key = os.getenv("LANGCHAIN_API_KEY")
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1", "yes")

    if api_key and tracing_enabled:
        # LangSmith will automatically pick up these env vars
        project = os.getenv("LANGCHAIN_PROJECT", "ski-lift-status")
        os.environ["LANGCHAIN_PROJECT"] = project

        logger = get_logger()
        logger.info("langsmith_enabled", project=project)
        return True

    return False


def create_langsmith_run_name(resort_id: str, phase: str) -> str:
    """Create a descriptive run name for LangSmith.

    Args:
        resort_id: The resort ID.
        phase: The pipeline phase.

    Returns:
        Formatted run name.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{phase}_{resort_id[:8]}_{timestamp}"


# Initialize logging on module import
configure_logging()
LANGSMITH_ENABLED = setup_langsmith()
