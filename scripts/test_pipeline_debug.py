#!/usr/bin/env python3
"""Debug script to test the scraping pipeline on specific resorts."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Enable debug mode
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "DEBUG"

from ski_lift_status.scraping.logging_config import get_logger, configure_logging
from ski_lift_status.scraping.page_loader import PageLoader
from ski_lift_status.scraping.classifier import ResourceClassifier
from ski_lift_status.scraping.schema_analyzer import SchemaAnalyzer
from ski_lift_status.scraping.pipeline import load_status_pages
from ski_lift_status.data_fetcher import load_lifts, load_runs

# Reconfigure logging with debug enabled
configure_logging()
logger = get_logger("test_pipeline_debug")


async def test_resort(resort_id: str, resort_name: str, status_url: str) -> dict:
    """Test the pipeline phases for a single resort."""
    log = logger.bind(resort_id=resort_id, resort_name=resort_name)
    log.info("=" * 60)
    log.info(f"TESTING: {resort_name}")
    log.info(f"URL: {status_url}")
    log.info("=" * 60)

    results = {
        "resort_id": resort_id,
        "resort_name": resort_name,
        "url": status_url,
        "phases": {},
        "errors": [],
    }

    # Load reference data
    all_lifts = load_lifts()
    all_runs = load_runs()

    resort_lifts = [l for l in all_lifts if resort_id in (l.ski_area_ids or "").split(";")]
    resort_runs = [r for r in all_runs if resort_id in (r.ski_area_ids or "").split(";")]

    log.info(
        "reference_data_loaded",
        lift_count=len(resort_lifts),
        run_count=len(resort_runs),
    )

    if len(resort_lifts) == 0 and len(resort_runs) == 0:
        log.warning("NO_REFERENCE_DATA - this resort has no lifts/runs in OpenSkiMap")
        results["errors"].append("No reference data in OpenSkiMap")

    # Phase 1: Page Load
    log.info("--- PHASE 1: Page Load ---")
    try:
        loader = PageLoader(headless=True, timeout_ms=60000, wait_after_load_ms=5000)
        capture = await loader.load_page(status_url, resort_id)

        results["phases"]["phase1"] = {
            "success": len(capture.errors) == 0,
            "resource_count": len(capture.resources),
            "load_time_ms": capture.load_time_ms,
            "errors": capture.errors,
            "resources": [
                {
                    "url": r.url[:100],
                    "type": r.resource_type.value,
                    "size": r.size_bytes,
                }
                for r in capture.resources
            ],
        }

        log.info(
            "phase1_complete",
            resource_count=len(capture.resources),
            load_time_ms=f"{capture.load_time_ms:.0f}",
            errors=capture.errors,
        )

    except Exception as e:
        log.error("phase1_failed", error=str(e))
        results["phases"]["phase1"] = {"success": False, "error": str(e)}
        results["errors"].append(f"Phase 1 failed: {e}")
        return results

    # Phase 2: Classification
    log.info("--- PHASE 2: Classification ---")
    try:
        classifier = ResourceClassifier(resort_id, resort_lifts, resort_runs)
        classified = classifier.classify_capture(capture)

        # Find best resources
        useful_resources = [c for c in classified if c.confidence_score > 0]

        results["phases"]["phase2"] = {
            "success": True,
            "total_classified": len(classified),
            "useful_resources": len(useful_resources),
            "best_resources": [
                {
                    "url": c.resource.url[:100],
                    "category": c.category.value,
                    "lift_coverage": f"{c.lift_coverage:.1%}",
                    "run_coverage": f"{c.run_coverage:.1%}",
                    "confidence": f"{c.confidence_score:.2f}",
                    "matched_lifts": c.matched_lift_names[:5],
                    "matched_runs": c.matched_run_names[:5],
                }
                for c in classified[:10]
            ],
        }

        log.info(
            "phase2_complete",
            total_classified=len(classified),
            useful_resources=len(useful_resources),
            best_confidence=classified[0].confidence_score if classified else 0,
        )

        if not useful_resources:
            log.warning("NO_USEFUL_RESOURCES - Classification found no resources with data coverage")
            results["errors"].append("No resources matched reference data")

    except Exception as e:
        log.error("phase2_failed", error=str(e))
        results["phases"]["phase2"] = {"success": False, "error": str(e)}
        results["errors"].append(f"Phase 2 failed: {e}")
        return results

    # Phase 3: Schema Analysis
    log.info("--- PHASE 3: Schema Analysis ---")
    try:
        analyzer = SchemaAnalyzer()
        schemas = analyzer.analyze_all(classified)

        total_schemas = sum(len(s) for s in schemas.values())
        best_schemas = analyzer.get_best_schemas(schemas, min_objects=1)

        results["phases"]["phase3"] = {
            "success": True,
            "total_schemas": total_schemas,
            "resources_with_schemas": len(schemas),
            "best_schemas": [
                {
                    "url": s.resource_url[:100],
                    "category": s.category.value,
                    "root_path": s.root_path,
                    "object_count": s.total_objects_count,
                    "fields": [f.name for f in s.fields[:10]],
                    "sample": s.sample_objects[0] if s.sample_objects else None,
                }
                for s in best_schemas[:5]
            ],
        }

        log.info(
            "phase3_complete",
            total_schemas=total_schemas,
            resources_with_schemas=len(schemas),
            best_schema_objects=best_schemas[0].total_objects_count if best_schemas else 0,
        )

        if not best_schemas:
            log.warning("NO_SCHEMAS - Could not parse any structured data")
            results["errors"].append("No parseable schemas found")

    except Exception as e:
        log.error("phase3_failed", error=str(e))
        results["phases"]["phase3"] = {"success": False, "error": str(e)}
        results["errors"].append(f"Phase 3 failed: {e}")

    return results


async def main():
    """Run E2E tests for the first 3 resorts."""
    logger.info("Starting E2E debug tests")

    # Load status pages
    status_pages = load_status_pages()

    if not status_pages:
        logger.error("No status pages found in data/status_pages.csv")
        return

    # Test first 3 (or all if less than 3)
    test_count = min(3, len(status_pages))
    logger.info(f"Testing {test_count} resorts")

    all_results = []

    for i, entry in enumerate(status_pages[:test_count]):
        logger.info(f"\n\n{'#' * 60}")
        logger.info(f"# Resort {i+1}/{test_count}")
        logger.info(f"{'#' * 60}\n")

        try:
            result = await test_resort(
                entry.resort_id,
                entry.resort_name,
                entry.status_page_url,
            )
            all_results.append(result)
        except Exception as e:
            logger.error(f"Test failed for {entry.resort_name}: {e}")
            all_results.append({
                "resort_id": entry.resort_id,
                "resort_name": entry.resort_name,
                "error": str(e),
            })

    # Print summary
    logger.info("\n\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    for result in all_results:
        name = result.get("resort_name", "Unknown")
        errors = result.get("errors", [])

        if errors:
            logger.warning(f"❌ {name}: {len(errors)} errors")
            for err in errors:
                logger.warning(f"   - {err}")
        else:
            phases = result.get("phases", {})
            p2 = phases.get("phase2", {})
            p3 = phases.get("phase3", {})
            logger.info(
                f"✓ {name}: {p2.get('useful_resources', 0)} useful resources, "
                f"{p3.get('total_schemas', 0)} schemas"
            )


if __name__ == "__main__":
    asyncio.run(main())
