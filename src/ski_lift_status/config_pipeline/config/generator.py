"""Config generator using GPT-5.1-Codex-Max.

This module uses OpenAI's GPT-5.1-Codex-Max model to generate extraction
configs based on the analysis output from the static tools.

It generates JavaScript extraction code when needed and creates
complete, tested configs.
"""

import json
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

import os
import httpx

from .schema import (
    ConfigSchema,
    DataSource,
    ExtractionMethod,
    NameMapping,
    validate_config,
)


@dataclass
class AnalysisContext:
    """Context from static analysis tools for config generation."""

    resort_id: str
    resort_name: str

    # Best resources identified by analysis
    lift_static_url: str | None = None
    lift_dynamic_url: str | None = None
    run_static_url: str | None = None
    run_dynamic_url: str | None = None

    # Schema information
    lift_static_schema: dict | None = None
    lift_dynamic_schema: dict | None = None
    run_static_schema: dict | None = None
    run_dynamic_schema: dict | None = None

    # Sample objects
    lift_samples: list[dict] = field(default_factory=list)
    run_samples: list[dict] = field(default_factory=list)

    # Foreign key information
    lift_foreign_key: str | None = None
    run_foreign_key: str | None = None

    # Name mappings already computed
    lift_mappings: list[dict] = field(default_factory=list)
    run_mappings: list[dict] = field(default_factory=list)

    # Coverage from name matching
    lift_coverage: float = 0.0
    run_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for LLM context."""
        return {
            "resort_id": self.resort_id,
            "resort_name": self.resort_name,
            "sources": {
                "lift_static": {"url": self.lift_static_url, "schema": self.lift_static_schema},
                "lift_dynamic": {"url": self.lift_dynamic_url, "schema": self.lift_dynamic_schema},
                "run_static": {"url": self.run_static_url, "schema": self.run_static_schema},
                "run_dynamic": {"url": self.run_dynamic_url, "schema": self.run_dynamic_schema},
            },
            "samples": {
                "lifts": self.lift_samples[:5],
                "runs": self.run_samples[:5],
            },
            "foreign_keys": {
                "lift": self.lift_foreign_key,
                "run": self.run_foreign_key,
            },
            "coverage": {
                "lift": self.lift_coverage,
                "run": self.run_coverage,
            },
        }


@dataclass
class GenerationResult:
    """Result of config generation."""

    success: bool
    config: ConfigSchema | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    debug_info: dict[str, Any] = field(default_factory=dict)


# System prompt for config generation
CONFIG_GENERATION_SYSTEM_PROMPT = """You are an expert at generating extraction configs for ski resort status data.

You will be given analysis results from static tools that have identified:
1. Which URLs contain lift and run status data
2. The schema/structure of the data
3. Sample objects showing the data format
4. Foreign key relationships between static and dynamic data

Your task is to generate a JSON config that can extract lift and run status data.

The config schema supports these extraction methods:
- json_path: For JSON APIs, use JSONPath-like selectors ($.field.subfield, $.array[*].field)
- css_selector: For HTML, use CSS selectors
- xpath: For HTML/XML, use XPath expressions
- javascript: For complex cases, generate safe extraction code

IMPORTANT rules for JavaScript extraction code:
1. DO NOT use fetch, XMLHttpRequest, or any network calls
2. DO NOT use eval, Function constructor, require, or import
3. DO NOT access process, fs, or any Node.js modules
4. The code receives the response content as a string parameter
5. Return an array of objects with {name, status, id?, type?} fields
6. Keep the code simple and focused on parsing/transforming data

Status mapping should normalize to these values:
- Lifts: "open", "closed", "hold", "wind_hold", "scheduled", "unknown"
- Runs: "open", "closed", "groomed", "moguls", "icy", "unknown"

Prefer JSON APIs over HTML scraping when available.
Prefer simple selectors over complex JavaScript.

Return a valid JSON config following this exact schema:
{
    "resort_id": "...",
    "resort_name": "...",
    "version": "1.0",
    "sources": [
        {
            "url": "...",
            "method": "GET",
            "headers": {},
            "content_type": "json" | "html",
            "data_types": ["lift_static", "lift_dynamic", "run_static", "run_dynamic"],
            "extraction_method": "json_path" | "css_selector" | "javascript",
            "list_selector": "$.path.to.array",
            "name_selector": "name_field",
            "status_selector": "status_field",
            "type_selector": "type_field",
            "id_selector": "id_field",
            "status_mapping": {"source_value": "normalized_value"},
            "extraction_code": null
        }
    ],
    "lift_foreign_key": null,
    "run_foreign_key": null,
    "lift_mappings": [],
    "run_mappings": []
}

Do NOT include the mappings in your response - those will be added separately.
Focus on getting the extraction selectors and status mapping correct."""


CONFIG_FIX_SYSTEM_PROMPT = """You are debugging a ski resort status extraction config that failed.

You will be given:
1. The current config that failed
2. The error messages and debug info
3. The original analysis context

Your task is to fix the config so it works correctly.

Common issues:
1. Wrong JSON path - check the sample data structure carefully
2. Wrong CSS selector - the class names might be dynamic/generated
3. Missing status mapping - add mappings for all status values seen
4. Wrong content_type - verify if it's JSON or HTML

When fixing JavaScript extraction code:
- Keep it simple and focused
- DO NOT add any network calls or dangerous operations
- Make sure it handles edge cases (null values, missing fields)

Return the complete fixed config as valid JSON."""


async def _call_codex(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> str | None:
    """Call LLM for config generation using OpenAI API via httpx."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set")
        return None

    # Use gpt-4o as primary model (best for complex code generation)
    # Falls back to gpt-4o-mini if needed
    models_to_try = ["gpt-4o", "gpt-4o-mini"]

    for model in models_to_try:
        try:
            async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 8000,
                        "response_format": {"type": "json_object"},
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    print(f"Model {model} returned status {response.status_code}: {response.text[:200]}")
                    continue

        except Exception as e:
            # Log error and try next model
            print(f"Model {model} failed: {e}")
            continue

    return None


def _parse_config_response(response: str, context: AnalysisContext) -> ConfigSchema | None:
    """Parse LLM response into ConfigSchema."""
    try:
        data = json.loads(response)

        # Ensure resort info
        data["resort_id"] = context.resort_id
        data["resort_name"] = context.resort_name

        # Add mappings from context
        data["lift_mappings"] = context.lift_mappings
        data["run_mappings"] = context.run_mappings

        # Add metadata
        data["created_at"] = datetime.utcnow().isoformat()

        return ConfigSchema.from_dict(data)

    except (json.JSONDecodeError, KeyError) as e:
        return None


class ConfigGenerator:
    """Generator for extraction configs using GPT-5.1-Codex-Max."""

    def __init__(self, max_attempts: int = 3):
        """Initialize generator."""
        self.max_attempts = max_attempts

    async def generate(
        self,
        context: AnalysisContext,
        test_callback: Any = None,  # async callable(config) -> (success, errors)
    ) -> GenerationResult:
        """Generate a config from analysis context.

        Args:
            context: Analysis results from static tools.
            test_callback: Optional async callback to test generated config.

        Returns:
            GenerationResult with generated config or errors.
        """
        result = GenerationResult(success=False)

        # Build user prompt with analysis context
        user_prompt = f"""Generate an extraction config for this ski resort:

Resort: {context.resort_name} (ID: {context.resort_id})

Analysis Results:
{json.dumps(context.to_dict(), indent=2)}

Please generate a complete config that will extract lift and run status data.
Return valid JSON only."""

        for attempt in range(self.max_attempts):
            result.attempts = attempt + 1

            # Generate config
            if attempt == 0:
                response = await _call_codex(CONFIG_GENERATION_SYSTEM_PROMPT, user_prompt)
            else:
                # Use fix prompt for retries
                fix_prompt = f"""The previous config attempt failed.

Previous config:
{result.config.to_json() if result.config else "None"}

Errors:
{json.dumps(result.errors[-5:], indent=2)}

Original analysis:
{json.dumps(context.to_dict(), indent=2)}

Please fix the config and return valid JSON."""

                response = await _call_codex(CONFIG_FIX_SYSTEM_PROMPT, fix_prompt)

            if not response:
                result.errors.append(f"Attempt {attempt + 1}: No response from model")
                continue

            # Parse response
            config = _parse_config_response(response, context)
            if not config:
                result.errors.append(f"Attempt {attempt + 1}: Failed to parse response as config")
                continue

            result.config = config

            # Validate config structure
            is_valid, validation_errors = validate_config(config)
            if not is_valid:
                result.errors.extend([f"Attempt {attempt + 1}: {e}" for e in validation_errors])
                continue

            # Test config if callback provided
            if test_callback:
                try:
                    test_success, test_errors = await test_callback(config)
                    if test_success:
                        result.success = True
                        return result
                    else:
                        result.errors.extend([f"Attempt {attempt + 1}: {e}" for e in test_errors])
                except Exception as e:
                    result.errors.append(f"Attempt {attempt + 1}: Test failed with exception: {e}")
            else:
                # No test callback, just return valid config
                result.success = True
                return result

        return result


async def generate_config(
    context: AnalysisContext,
    max_attempts: int = 3,
) -> GenerationResult:
    """Generate a config from analysis context.

    This is the main entry point for config generation.

    Args:
        context: Analysis results from static tools.
        max_attempts: Maximum generation attempts.

    Returns:
        GenerationResult with generated config or errors.
    """
    generator = ConfigGenerator(max_attempts=max_attempts)
    return await generator.generate(context)
