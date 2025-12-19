"""Config generation and execution module.

This module handles:
- Config schema definition
- Secure JavaScript config execution in sandbox
- Config generation using GPT-5.1-Codex-Max
- Config validation and testing
"""

from .schema import (
    LiftStatus,
    RunStatus,
    DataSource,
    ExtractionMethod,
    ConfigSchema,
    NameMapping as ConfigNameMapping,
    validate_config,
)
from .runner import (
    ConfigRunner,
    ExecutionResult,
    run_config,
    test_config_coverage,
)
from .generator import (
    ConfigGenerator,
    GenerationResult,
    generate_config,
)

__all__ = [
    # Schema
    "LiftStatus",
    "RunStatus",
    "DataSource",
    "ExtractionMethod",
    "ConfigSchema",
    "ConfigNameMapping",
    "validate_config",
    # Runner
    "ConfigRunner",
    "ExecutionResult",
    "run_config",
    "test_config_coverage",
    # Generator
    "ConfigGenerator",
    "GenerationResult",
    "generate_config",
]
