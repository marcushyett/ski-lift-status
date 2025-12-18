"""Resource classifier for identifying static vs dynamic data."""

import re

from ..models import Lift, Run
from ..data_fetcher import load_lifts, load_runs
from .logging_config import get_logger, save_debug_artifact
from .models import (
    CapturedResource,
    ClassifiedResource,
    DataCategory,
    NetworkCapture,
    ResourceType,
)

logger = get_logger(__name__)


# Keywords that indicate dynamic/status data
STATUS_KEYWORDS = [
    "status",
    "open",
    "closed",
    "operating",
    "running",
    "available",
    "unavailable",
    "wait",
    "queue",
    "time",
    "delay",
    "condition",
    "groomed",
    "powder",
    "packed",
    "icy",
    "wind",
    "hold",
    "suspended",
    "maintenance",
    "ouvert",  # French
    "fermé",   # French
    "ferme",   # French without accent
    "offen",   # German
    "geschlossen",  # German
    "aperto",  # Italian
    "chiuso",  # Italian
]

# Keywords that indicate static/metadata
METADATA_KEYWORDS = [
    "name",
    "type",
    "category",
    "difficulty",
    "elevation",
    "length",
    "capacity",
    "vertical",
    "coordinates",
    "location",
    "description",
    "nom",      # French
    "typ",      # German
    "nome",     # Italian
]


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison."""
    if not name:
        return ""
    # Remove special characters and extra spaces, lowercase
    normalized = re.sub(r"[^\w\s]", " ", name.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _calculate_coverage(
    content: str,
    reference_names: list[str],
) -> tuple[float, list[str]]:
    """Calculate what percentage of reference names appear in content.

    Args:
        content: The content to search in.
        reference_names: List of names to look for.

    Returns:
        Tuple of (coverage percentage, list of matched names).
    """
    if not reference_names:
        return 0.0, []

    content_normalized = _normalize_name(content)
    matched = []

    for name in reference_names:
        if not name:
            continue

        name_normalized = _normalize_name(name)
        if not name_normalized:
            continue

        # Check for exact match in normalized content
        if name_normalized in content_normalized:
            matched.append(name)
            continue

        # Check for partial match (at least 2 words match)
        name_words = name_normalized.split()
        if len(name_words) >= 2:
            # Check if most words appear in content
            matching_words = sum(1 for w in name_words if w in content_normalized)
            if matching_words >= len(name_words) * 0.7:
                matched.append(name)

    coverage = len(matched) / len(reference_names) if reference_names else 0.0
    return coverage, matched


def _contains_status_keywords(content: str) -> bool:
    """Check if content contains status-related keywords."""
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in STATUS_KEYWORDS)


def _contains_metadata_keywords(content: str) -> bool:
    """Check if content contains metadata-related keywords."""
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in METADATA_KEYWORDS)


def _determine_category(
    lift_coverage: float,
    run_coverage: float,
    has_status_keywords: bool,
    has_metadata_keywords: bool,
) -> DataCategory:
    """Determine the data category based on analysis results."""
    # Need at least some coverage to be useful
    min_coverage = 0.05  # 5%

    has_coverage = lift_coverage >= min_coverage or run_coverage >= min_coverage

    if not has_coverage:
        return DataCategory.UNKNOWN

    if has_status_keywords and has_metadata_keywords:
        return DataCategory.MIXED
    elif has_status_keywords:
        return DataCategory.DYNAMIC_STATUS
    elif has_metadata_keywords:
        return DataCategory.STATIC_METADATA
    else:
        # Has coverage but unclear type - assume mixed
        return DataCategory.MIXED


def _calculate_confidence(
    lift_coverage: float,
    run_coverage: float,
    category: DataCategory,
) -> float:
    """Calculate confidence score for classification."""
    if category == DataCategory.UNKNOWN:
        return 0.0

    # Base confidence on coverage
    max_coverage = max(lift_coverage, run_coverage)

    # Scale: 0.1 coverage = 0.5 confidence, 0.5 coverage = 0.8 confidence
    if max_coverage < 0.1:
        confidence = max_coverage * 5  # 0-0.5
    elif max_coverage < 0.5:
        confidence = 0.5 + (max_coverage - 0.1) * 0.75  # 0.5-0.8
    else:
        confidence = 0.8 + (max_coverage - 0.5) * 0.4  # 0.8-1.0

    return min(1.0, confidence)


class ResourceClassifier:
    """Classifies captured resources by their data category."""

    def __init__(
        self,
        resort_id: str,
        lifts: list[Lift] | None = None,
        runs: list[Run] | None = None,
    ):
        """Initialize the classifier.

        Args:
            resort_id: The resort ID to get reference data for.
            lifts: Optional list of lifts. If None, loads from data files.
            runs: Optional list of runs. If None, loads from data files.
        """
        self.resort_id = resort_id
        self.log = logger.bind(resort_id=resort_id, phase="classify")

        # Load reference data
        if lifts is None:
            all_lifts = load_lifts()
            self.lifts = [
                l for l in all_lifts if resort_id in (l.ski_area_ids or "").split(";")
            ]
        else:
            self.lifts = lifts

        if runs is None:
            all_runs = load_runs()
            self.runs = [
                r for r in all_runs if resort_id in (r.ski_area_ids or "").split(";")
            ]
        else:
            self.runs = runs

        # Extract names for matching
        self.lift_names = [l.name for l in self.lifts if l.name]
        self.run_names = [r.name for r in self.runs if r.name]

        self.log.info(
            "classifier_initialized",
            lift_count=len(self.lifts),
            run_count=len(self.runs),
            lift_names_sample=self.lift_names[:5],
            run_names_sample=self.run_names[:5],
        )

    def classify_resource(self, resource: CapturedResource) -> ClassifiedResource:
        """Classify a single captured resource.

        Args:
            resource: The captured resource to classify.

        Returns:
            ClassifiedResource with category and coverage info.
        """
        content = resource.content

        # Calculate coverage
        lift_coverage, matched_lifts = _calculate_coverage(content, self.lift_names)
        run_coverage, matched_runs = _calculate_coverage(content, self.run_names)

        # Check for keywords
        has_status = _contains_status_keywords(content)
        has_metadata = _contains_metadata_keywords(content)

        # Determine category
        category = _determine_category(
            lift_coverage, run_coverage, has_status, has_metadata
        )

        # Calculate confidence
        confidence = _calculate_confidence(lift_coverage, run_coverage, category)

        self.log.debug(
            "resource_classified",
            url=resource.url[:80],
            resource_type=resource.resource_type if isinstance(resource.resource_type, str) else resource.resource_type.value,
            category=category.value,
            lift_coverage=f"{lift_coverage:.1%}",
            run_coverage=f"{run_coverage:.1%}",
            matched_lifts_count=len(matched_lifts),
            matched_runs_count=len(matched_runs),
            has_status_keywords=has_status,
            has_metadata_keywords=has_metadata,
            confidence=f"{confidence:.2f}",
        )

        return ClassifiedResource(
            resource=resource,
            category=category,
            lift_coverage=lift_coverage,
            run_coverage=run_coverage,
            matched_lift_names=matched_lifts,
            matched_run_names=matched_runs,
            contains_status_keywords=has_status,
            confidence_score=confidence,
        )

    def classify_capture(
        self,
        capture: NetworkCapture,
        min_confidence: float = 0.0,  # Changed default to 0 to see all results
    ) -> list[ClassifiedResource]:
        """Classify all resources in a network capture.

        Args:
            capture: The network capture to classify.
            min_confidence: Minimum confidence score to include.

        Returns:
            List of ClassifiedResource objects, sorted by confidence.
        """
        self.log.info(
            "starting_classification",
            resource_count=len(capture.resources),
            has_page_html=capture.page_html is not None,
        )

        classified = []

        for resource in capture.resources:
            result = self.classify_resource(resource)
            if result.confidence_score >= min_confidence:
                classified.append(result)

        # Also classify the page HTML if present
        if capture.page_html:
            html_resource = CapturedResource(
                url=capture.status_page_url,
                resource_type=ResourceType.HTML,
                content_type="text/html",
                content=capture.page_html,
                size_bytes=len(capture.page_html.encode("utf-8")),
                response_status=200,
            )
            result = self.classify_resource(html_resource)
            if result.confidence_score >= min_confidence:
                classified.append(result)

        # Sort by confidence, highest first
        classified.sort(key=lambda x: x.confidence_score, reverse=True)

        # Log summary
        categories_summary = {}
        for c in classified:
            cat = c.category.value
            categories_summary[cat] = categories_summary.get(cat, 0) + 1

        self.log.info(
            "classification_complete",
            total_classified=len(classified),
            by_category=categories_summary,
            top_confidence=classified[0].confidence_score if classified else 0,
            top_url=classified[0].resource.url[:80] if classified else None,
        )

        # Save debug artifact
        save_debug_artifact(
            "classification_results",
            {
                "total_resources": len(capture.resources) + (1 if capture.page_html else 0),
                "classified_count": len(classified),
                "reference_lifts": self.lift_names,
                "reference_runs": self.run_names,
                "results": [
                    {
                        "url": r.resource.url,
                        "category": r.category.value,
                        "lift_coverage": r.lift_coverage,
                        "run_coverage": r.run_coverage,
                        "confidence": r.confidence_score,
                        "matched_lifts": r.matched_lift_names[:10],
                        "matched_runs": r.matched_run_names[:10],
                    }
                    for r in classified[:20]  # Top 20
                ],
            },
            resort_id=self.resort_id,
            phase="phase2_classify",
        )

        return classified

    def get_best_sources(
        self,
        classified_resources: list[ClassifiedResource],
        category: DataCategory | None = None,
    ) -> list[ClassifiedResource]:
        """Get the best sources for a given category.

        Args:
            classified_resources: List of classified resources.
            category: Optional category filter.

        Returns:
            Filtered and sorted list of best sources.
        """
        if category:
            filtered = [r for r in classified_resources if r.category == category]
        else:
            filtered = [
                r
                for r in classified_resources
                if r.category != DataCategory.UNKNOWN
            ]

        return sorted(filtered, key=lambda x: x.confidence_score, reverse=True)


def classify_network_capture(
    capture: NetworkCapture,
    resort_id: str,
    lifts: list[Lift] | None = None,
    runs: list[Run] | None = None,
) -> list[ClassifiedResource]:
    """Convenience function to classify a network capture.

    Args:
        capture: The network capture to classify.
        resort_id: The resort ID.
        lifts: Optional list of lifts for reference.
        runs: Optional list of runs for reference.

    Returns:
        List of ClassifiedResource objects.
    """
    classifier = ResourceClassifier(resort_id, lifts, runs)
    return classifier.classify_capture(capture)
