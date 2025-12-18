"""LLM-based configuration generator for extraction configs."""

import json
import os
from typing import Any

from openai import OpenAI

from .models import (
    ExtractionConfig,
    ExtractionType,
    FieldMapping,
    PipelineConfig,
    SchemaOverview,
    SourceMapping,
)


# System prompt for the LLM
SYSTEM_PROMPT = """You are an expert at generating data extraction configurations for ski resort status pages.

Given schema information about data sources, generate extraction configurations that can reliably extract:
1. Lift information: name, status, type, and any identifiers
2. Run information: name, status, difficulty, and any identifiers

You must output valid JSON matching the required schema. Be precise with selectors and paths.

For JSON data:
- Use JSONPath expressions (e.g., "$.lifts[*].name")
- Identify the root array path and field mappings

For HTML data:
- Use CSS selectors (e.g., "div.lift-item .name")
- Or XPath expressions if needed (e.g., "//div[@class='lift']//span[@class='name']")

Always prefer simpler, more robust selectors that are less likely to break with minor page changes."""


def _create_extraction_prompt(
    schema: SchemaOverview,
    sample_content: str | None = None,
) -> str:
    """Create a prompt for generating extraction config."""
    prompt_parts = [
        "Generate an extraction configuration for the following data source.",
        "",
        f"Resource URL: {schema.resource_url}",
        f"Data Category: {schema.category.value}",
        f"Root Path: {schema.root_path or 'N/A'}",
        f"Total Objects: {schema.total_objects_count}",
        "",
        "Fields discovered:",
    ]

    for field in schema.fields:
        field_info = f"  - {field.name} ({field.field_type})"
        if field.is_name_field:
            field_info += " [NAME FIELD]"
        if field.is_status_field:
            field_info += " [STATUS FIELD]"
        if field.is_identifier:
            field_info += " [IDENTIFIER]"
        if field.sample_values:
            samples = ", ".join(str(v)[:50] for v in field.sample_values[:3])
            field_info += f" - samples: {samples}"
        prompt_parts.append(field_info)

    prompt_parts.extend([
        "",
        "Sample objects:",
        json.dumps(schema.sample_objects, indent=2)[:2000],  # Limit size
        "",
    ])

    if sample_content:
        prompt_parts.extend([
            "Sample content (truncated):",
            sample_content[:1000],
            "",
        ])

    prompt_parts.extend([
        "Output a JSON object with the following structure:",
        """{
  "extraction_type": "json_path" | "css_selector" | "xpath",
  "root_selector": "path to array of items",
  "lift_name_selector": "selector for lift name",
  "lift_status_selector": "selector for lift status",
  "lift_type_selector": "selector for lift type (optional)",
  "lift_id_selector": "selector for lift ID (optional)",
  "run_name_selector": "selector for run name",
  "run_status_selector": "selector for run status",
  "run_difficulty_selector": "selector for run difficulty (optional)",
  "run_id_selector": "selector for run ID (optional)",
  "field_mappings": [
    {"source_field": "original_field", "target_field": "standard_field", "transformation": null}
  ]
}""",
        "",
        "Only include selectors for data that exists in the source. Use null for missing fields.",
    ])

    return "\n".join(prompt_parts)


def _parse_llm_response(response_text: str) -> dict[str, Any]:
    """Parse the LLM response into a config dict."""
    # Try to extract JSON from the response
    try:
        # First try direct parse
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code blocks
    import re
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object
    brace_match = re.search(r"\{[\s\S]*\}", response_text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse JSON from LLM response")


def _dict_to_extraction_config(
    config_dict: dict[str, Any],
    schema: SchemaOverview,
) -> ExtractionConfig:
    """Convert a config dict to an ExtractionConfig object."""
    # Parse extraction type
    extraction_type_str = config_dict.get("extraction_type", "json_path")
    try:
        extraction_type = ExtractionType(extraction_type_str)
    except ValueError:
        extraction_type = ExtractionType.JSON_PATH

    # Parse field mappings
    field_mappings = []
    for mapping in config_dict.get("field_mappings", []):
        if isinstance(mapping, dict):
            field_mappings.append(FieldMapping(
                source_field=mapping.get("source_field", ""),
                target_field=mapping.get("target_field", ""),
                transformation=mapping.get("transformation"),
            ))

    return ExtractionConfig(
        resource_url=schema.resource_url,
        extraction_type=extraction_type,
        category=schema.category,
        root_selector=config_dict.get("root_selector"),
        field_mappings=field_mappings,
        lift_name_selector=config_dict.get("lift_name_selector"),
        lift_status_selector=config_dict.get("lift_status_selector"),
        lift_type_selector=config_dict.get("lift_type_selector"),
        lift_id_selector=config_dict.get("lift_id_selector"),
        run_name_selector=config_dict.get("run_name_selector"),
        run_status_selector=config_dict.get("run_status_selector"),
        run_difficulty_selector=config_dict.get("run_difficulty_selector"),
        run_id_selector=config_dict.get("run_id_selector"),
        expected_item_count=schema.total_objects_count,
    )


class ConfigGenerator:
    """Generates extraction configurations using an LLM."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
    ):
        """Initialize the config generator.

        Args:
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
            model: The model to use for generation.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("OpenAI API key is required")
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def generate_config(
        self,
        schema: SchemaOverview,
        sample_content: str | None = None,
    ) -> ExtractionConfig:
        """Generate an extraction config for a schema.

        Args:
            schema: The schema to generate config for.
            sample_content: Optional sample content for context.

        Returns:
            ExtractionConfig for the schema.
        """
        prompt = _create_extraction_prompt(schema, sample_content)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # Low temperature for consistent output
            response_format={"type": "json_object"},
        )

        response_text = response.choices[0].message.content or "{}"
        config_dict = _parse_llm_response(response_text)

        return _dict_to_extraction_config(config_dict, schema)

    def generate_pipeline_config(
        self,
        resort_id: str,
        resort_name: str,
        status_page_url: str,
        schemas: list[SchemaOverview],
        source_mappings: list[SourceMapping],
        sample_contents: dict[str, str] | None = None,
    ) -> PipelineConfig:
        """Generate a complete pipeline configuration.

        Args:
            resort_id: The resort ID.
            resort_name: The resort name.
            status_page_url: The status page URL.
            schemas: List of schemas to generate configs for.
            source_mappings: Source mappings for cross-referencing.
            sample_contents: Optional dict of URL -> sample content.

        Returns:
            Complete PipelineConfig.
        """
        from datetime import datetime

        sample_contents = sample_contents or {}
        extraction_configs = []

        for schema in schemas:
            sample_content = sample_contents.get(schema.resource_url)
            config = self.generate_config(schema, sample_content)
            extraction_configs.append(config)

        return PipelineConfig(
            resort_id=resort_id,
            resort_name=resort_name,
            status_page_url=status_page_url,
            extraction_configs=extraction_configs,
            source_mappings=source_mappings,
            generated_at=datetime.utcnow().isoformat(),
            generation_attempts=1,
        )


class MockConfigGenerator:
    """Mock config generator for testing without API calls."""

    def generate_config(
        self,
        schema: SchemaOverview,
        sample_content: str | None = None,
    ) -> ExtractionConfig:
        """Generate a basic extraction config based on schema analysis."""
        # Determine extraction type based on content
        if schema.root_path and schema.root_path.startswith("$"):
            extraction_type = ExtractionType.JSON_PATH
        else:
            extraction_type = ExtractionType.CSS_SELECTOR

        # Find relevant fields
        name_field = next(
            (f.name for f in schema.fields if f.is_name_field), None
        )
        status_field = next(
            (f.name for f in schema.fields if f.is_status_field), None
        )
        id_field = next(
            (f.name for f in schema.fields if f.is_identifier), None
        )

        # Build selectors based on extraction type
        if extraction_type == ExtractionType.JSON_PATH:
            root_selector = schema.root_path
            name_selector = f"$.{name_field}" if name_field else None
            status_selector = f"$.{status_field}" if status_field else None
            id_selector = f"$.{id_field}" if id_field else None
        else:
            root_selector = schema.root_path
            name_selector = f".{name_field}" if name_field else None
            status_selector = f".{status_field}" if status_field else None
            id_selector = f".{id_field}" if id_field else None

        return ExtractionConfig(
            resource_url=schema.resource_url,
            extraction_type=extraction_type,
            category=schema.category,
            root_selector=root_selector,
            lift_name_selector=name_selector,
            lift_status_selector=status_selector,
            lift_id_selector=id_selector,
            run_name_selector=name_selector,
            run_status_selector=status_selector,
            run_id_selector=id_selector,
            expected_item_count=schema.total_objects_count,
        )

    def generate_pipeline_config(
        self,
        resort_id: str,
        resort_name: str,
        status_page_url: str,
        schemas: list[SchemaOverview],
        source_mappings: list[SourceMapping],
        sample_contents: dict[str, str] | None = None,
    ) -> PipelineConfig:
        """Generate a pipeline config without API calls."""
        from datetime import datetime

        extraction_configs = []
        for schema in schemas:
            config = self.generate_config(schema)
            extraction_configs.append(config)

        return PipelineConfig(
            resort_id=resort_id,
            resort_name=resort_name,
            status_page_url=status_page_url,
            extraction_configs=extraction_configs,
            source_mappings=source_mappings,
            generated_at=datetime.utcnow().isoformat(),
            generation_attempts=1,
        )


def get_config_generator(use_mock: bool = False) -> ConfigGenerator | MockConfigGenerator:
    """Get a config generator instance.

    Args:
        use_mock: If True, return a mock generator that doesn't use API.

    Returns:
        ConfigGenerator or MockConfigGenerator instance.
    """
    if use_mock or not os.getenv("OPENAI_API_KEY"):
        return MockConfigGenerator()
    return ConfigGenerator()
