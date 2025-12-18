"""Main pipeline orchestrator for the scraping workflow."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..data_fetcher import load_lifts, load_resorts, load_runs
from ..models import Lift, Resort, Run
from ..utils import get_data_dir
from .agent import ScrapingAgent, run_scraping_agent
from .classifier import ResourceClassifier, classify_network_capture
from .config_generator import ConfigGenerator, MockConfigGenerator, get_config_generator
from .models import (
    ClassifiedResource,
    DataCategory,
    NetworkCapture,
    PipelineConfig,
    PipelineResult,
    SchemaOverview,
    SourceMapping,
)
from .page_loader import PageLoader, capture_page_resources
from .schema_analyzer import SchemaAnalyzer, analyze_classified_resources
from .source_mapper import SourceMapper, find_source_mappings


@dataclass
class StatusPageEntry:
    """Entry from the status_pages.csv file."""

    resort_id: str
    resort_name: str
    website_url: str
    status_page_url: str


def load_status_pages(path: Path | None = None) -> list[StatusPageEntry]:
    """Load status page entries from CSV.

    Args:
        path: Path to the CSV file. If None, uses default location.

    Returns:
        List of StatusPageEntry objects.
    """
    if path is None:
        path = get_data_dir() / "status_pages.csv"

    if not path.exists():
        return []

    entries = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = StatusPageEntry(
                resort_id=row.get("resort_id", ""),
                resort_name=row.get("resort_name", ""),
                website_url=row.get("website_url", ""),
                status_page_url=row.get("status_page_url", ""),
            )
            entries.append(entry)

    return entries


def save_pipeline_config(config: PipelineConfig, path: Path | None = None) -> Path:
    """Save a pipeline config to JSON file.

    Args:
        config: The config to save.
        path: Output path. If None, uses default location.

    Returns:
        Path to the saved file.
    """
    if path is None:
        configs_dir = get_data_dir() / "configs"
        configs_dir.mkdir(exist_ok=True)
        path = configs_dir / f"{config.resort_id}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2)

    return path


def load_pipeline_config(resort_id: str, path: Path | None = None) -> PipelineConfig | None:
    """Load a pipeline config from JSON file.

    Args:
        resort_id: The resort ID to load config for.
        path: Path to the config file. If None, uses default location.

    Returns:
        PipelineConfig if found, None otherwise.
    """
    if path is None:
        path = get_data_dir() / "configs" / f"{resort_id}.json"

    if not path.exists():
        return None

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        return PipelineConfig(**data)


class ScrapingPipeline:
    """Main orchestrator for the scraping pipeline."""

    def __init__(
        self,
        headless: bool = True,
        use_mock_llm: bool = False,
        max_attempts: int = 3,
        min_coverage: float = 0.20,
    ):
        """Initialize the pipeline.

        Args:
            headless: Run browser in headless mode.
            use_mock_llm: Use mock LLM for testing.
            max_attempts: Maximum config refinement attempts.
            min_coverage: Minimum coverage threshold (20% default).
        """
        self.page_loader = PageLoader(headless=headless)
        self.config_generator = get_config_generator(use_mock=use_mock_llm)
        self.schema_analyzer = SchemaAnalyzer()
        self.max_attempts = max_attempts
        self.min_coverage = min_coverage

        # Load reference data
        self.resorts = load_resorts()
        self.lifts = load_lifts()
        self.runs = load_runs()

    def _get_resort_lifts(self, resort_id: str) -> list[Lift]:
        """Get lifts for a specific resort."""
        return [
            l for l in self.lifts
            if resort_id in (l.ski_area_ids or "").split(";")
        ]

    def _get_resort_runs(self, resort_id: str) -> list[Run]:
        """Get runs for a specific resort."""
        return [
            r for r in self.runs
            if resort_id in (r.ski_area_ids or "").split(";")
        ]

    async def run_phase1_capture(
        self,
        url: str,
        resort_id: str,
    ) -> NetworkCapture:
        """Phase 1: Capture network traffic from page.

        Args:
            url: Status page URL.
            resort_id: Resort ID.

        Returns:
            NetworkCapture with all captured resources.
        """
        print(f"Phase 1: Loading page and capturing network traffic...")
        capture = await self.page_loader.load_page(url, resort_id)
        print(f"  Captured {len(capture.resources)} resources in {capture.load_time_ms:.0f}ms")
        return capture

    def run_phase2_classify(
        self,
        capture: NetworkCapture,
        resort_id: str,
    ) -> list[ClassifiedResource]:
        """Phase 2: Classify captured resources.

        Args:
            capture: Network capture from phase 1.
            resort_id: Resort ID.

        Returns:
            List of classified resources.
        """
        print(f"Phase 2: Classifying resources...")
        resort_lifts = self._get_resort_lifts(resort_id)
        resort_runs = self._get_resort_runs(resort_id)

        classifier = ResourceClassifier(resort_id, resort_lifts, resort_runs)
        classified = classifier.classify_capture(capture)

        # Log classification results
        categories = {}
        for c in classified:
            cat = c.category.value
            categories[cat] = categories.get(cat, 0) + 1

        print(f"  Classified {len(classified)} resources:")
        for cat, count in categories.items():
            print(f"    - {cat}: {count}")

        return classified

    def run_phase3_analyze(
        self,
        classified: list[ClassifiedResource],
    ) -> dict[str, list[SchemaOverview]]:
        """Phase 3: Analyze schemas and extract samples.

        Args:
            classified: Classified resources from phase 2.

        Returns:
            Dict of URL -> SchemaOverview list.
        """
        print(f"Phase 3: Analyzing schemas...")
        schemas = self.schema_analyzer.analyze_all(classified)

        total_schemas = sum(len(s) for s in schemas.values())
        print(f"  Found {total_schemas} schemas across {len(schemas)} resources")

        return schemas

    def run_phase4_map(
        self,
        schemas: dict[str, list[SchemaOverview]],
        resort_id: str,
    ) -> list[SourceMapping]:
        """Phase 4: Map relationships between sources.

        Args:
            schemas: Schemas from phase 3.
            resort_id: Resort ID.

        Returns:
            List of source mappings.
        """
        print(f"Phase 4: Mapping source relationships...")
        resort_lifts = self._get_resort_lifts(resort_id)
        resort_runs = self._get_resort_runs(resort_id)

        mapper = SourceMapper(resort_lifts, resort_runs)
        mappings = mapper.find_all_mappings(schemas)

        print(f"  Found {len(mappings)} source mappings")

        return mappings

    def run_phase5_generate(
        self,
        resort_id: str,
        resort_name: str,
        status_page_url: str,
        schemas: dict[str, list[SchemaOverview]],
        mappings: list[SourceMapping],
        sample_contents: dict[str, str],
    ) -> PipelineConfig:
        """Phase 5: Generate extraction configuration.

        Args:
            resort_id: Resort ID.
            resort_name: Resort name.
            status_page_url: Status page URL.
            schemas: Schemas from phase 3.
            mappings: Mappings from phase 4.
            sample_contents: Sample content for each URL.

        Returns:
            Generated PipelineConfig.
        """
        print(f"Phase 5: Generating extraction configuration...")

        # Get best schemas
        best_schemas = self.schema_analyzer.get_best_schemas(schemas)[:5]

        config = self.config_generator.generate_pipeline_config(
            resort_id=resort_id,
            resort_name=resort_name,
            status_page_url=status_page_url,
            schemas=best_schemas,
            source_mappings=mappings,
            sample_contents=sample_contents,
        )

        print(f"  Generated {len(config.extraction_configs)} extraction configs")

        return config

    def run_phase6_refine(
        self,
        config: PipelineConfig,
        schemas: dict[str, list[SchemaOverview]],
        sample_contents: dict[str, str],
        resort_id: str,
    ) -> PipelineResult:
        """Phase 6: Iteratively refine and validate configuration.

        Args:
            config: Configuration from phase 5.
            schemas: Schemas from phase 3.
            sample_contents: Sample content for each URL.
            resort_id: Resort ID.

        Returns:
            Final PipelineResult.
        """
        print(f"Phase 6: Refining configuration (max {self.max_attempts} attempts)...")

        resort_lifts = self._get_resort_lifts(resort_id)
        resort_runs = self._get_resort_runs(resort_id)

        # Flatten schemas
        all_schemas = []
        for schema_list in schemas.values():
            all_schemas.extend(schema_list)

        result = run_scraping_agent(
            config=config,
            schemas=all_schemas,
            sample_contents=sample_contents,
            reference_lifts=resort_lifts,
            reference_runs=resort_runs,
            max_attempts=self.max_attempts,
            min_coverage=self.min_coverage,
        )

        if result.success:
            print(f"  SUCCESS! Coverage: lifts={result.lift_coverage:.1%}, runs={result.run_coverage:.1%}")
        else:
            print(f"  FAILED. Coverage: lifts={result.lift_coverage:.1%}, runs={result.run_coverage:.1%}")

        return result

    async def run_for_resort(
        self,
        resort_id: str,
        status_page_url: str,
        resort_name: str | None = None,
    ) -> PipelineResult:
        """Run the complete pipeline for a single resort.

        Args:
            resort_id: The resort ID.
            status_page_url: The status page URL.
            resort_name: Optional resort name.

        Returns:
            PipelineResult with extraction results.
        """
        print(f"\n{'='*60}")
        print(f"Running pipeline for: {resort_name or resort_id}")
        print(f"URL: {status_page_url}")
        print(f"{'='*60}\n")

        # Get resort name if not provided
        if not resort_name:
            resort = next((r for r in self.resorts if r.id == resort_id), None)
            resort_name = resort.name if resort else resort_id

        # Phase 1: Capture
        capture = await self.run_phase1_capture(status_page_url, resort_id)

        if capture.errors:
            print(f"  Warnings: {capture.errors}")

        # Phase 2: Classify
        classified = self.run_phase2_classify(capture, resort_id)

        if not classified:
            return PipelineResult(
                resort_id=resort_id,
                success=False,
                errors=["No relevant resources found in page"],
            )

        # Phase 3: Analyze
        schemas = self.run_phase3_analyze(classified)

        if not schemas:
            return PipelineResult(
                resort_id=resort_id,
                success=False,
                errors=["No parseable schemas found"],
            )

        # Phase 4: Map
        mappings = self.run_phase4_map(schemas, resort_id)

        # Prepare sample contents
        sample_contents = {
            r.resource.url: r.resource.content
            for r in classified
        }

        # Phase 5: Generate
        config = self.run_phase5_generate(
            resort_id=resort_id,
            resort_name=resort_name,
            status_page_url=status_page_url,
            schemas=schemas,
            mappings=mappings,
            sample_contents=sample_contents,
        )

        # Phase 6: Refine
        result = self.run_phase6_refine(config, schemas, sample_contents, resort_id)

        # Save config if successful
        if result.success and result.config:
            config_path = save_pipeline_config(result.config)
            print(f"\nSaved config to: {config_path}")

        return result

    async def run_for_all(
        self,
        status_pages: list[StatusPageEntry] | None = None,
    ) -> dict[str, PipelineResult]:
        """Run the pipeline for all configured status pages.

        Args:
            status_pages: Optional list of status pages. If None, loads from file.

        Returns:
            Dict of resort_id -> PipelineResult.
        """
        if status_pages is None:
            status_pages = load_status_pages()

        results = {}

        for entry in status_pages:
            result = await self.run_for_resort(
                resort_id=entry.resort_id,
                status_page_url=entry.status_page_url,
                resort_name=entry.resort_name,
            )
            results[entry.resort_id] = result

        # Print summary
        print(f"\n{'='*60}")
        print("PIPELINE SUMMARY")
        print(f"{'='*60}")

        successful = sum(1 for r in results.values() if r.success)
        print(f"\nTotal: {len(results)} resorts")
        print(f"Successful: {successful}")
        print(f"Failed: {len(results) - successful}")

        if successful > 0:
            avg_lift_coverage = sum(
                r.lift_coverage for r in results.values() if r.success
            ) / successful
            avg_run_coverage = sum(
                r.run_coverage for r in results.values() if r.success
            ) / successful
            print(f"Avg lift coverage: {avg_lift_coverage:.1%}")
            print(f"Avg run coverage: {avg_run_coverage:.1%}")

        return results


async def run_pipeline_for_resort(
    resort_id: str,
    status_page_url: str,
    resort_name: str | None = None,
    headless: bool = True,
    use_mock_llm: bool = False,
) -> PipelineResult:
    """Convenience function to run pipeline for a single resort.

    Args:
        resort_id: The resort ID.
        status_page_url: The status page URL.
        resort_name: Optional resort name.
        headless: Run browser in headless mode.
        use_mock_llm: Use mock LLM for testing.

    Returns:
        PipelineResult with extraction results.
    """
    pipeline = ScrapingPipeline(headless=headless, use_mock_llm=use_mock_llm)
    return await pipeline.run_for_resort(resort_id, status_page_url, resort_name)


async def run_pipeline_for_all(
    headless: bool = True,
    use_mock_llm: bool = False,
) -> dict[str, PipelineResult]:
    """Convenience function to run pipeline for all configured resorts.

    Args:
        headless: Run browser in headless mode.
        use_mock_llm: Use mock LLM for testing.

    Returns:
        Dict of resort_id -> PipelineResult.
    """
    pipeline = ScrapingPipeline(headless=headless, use_mock_llm=use_mock_llm)
    return await pipeline.run_for_all()
