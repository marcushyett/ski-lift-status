"""Tests for status word finder."""

import pytest
from ski_lift_status.config_pipeline.analysis.status_finder import (
    StatusMatch,
    StatusFinderResult,
    LIFT_INDICATOR_WORDS,
    RUN_INDICATOR_WORDS,
    STATUS_WORDS,
    find_status_indicators,
    analyze_resources_for_status,
)


class TestFindStatusIndicators:
    """Tests for find_status_indicators function."""

    def test_english_status_words(self):
        """Test finding English status words."""
        content = "The gondola is open. Chair 1 is closed. Chair 2 is on hold."

        result = find_status_indicators(content)

        assert result.status_word_count >= 3
        assert any(m.word == "open" for m in result.status_matches)
        assert any(m.word == "closed" for m in result.status_matches)

    def test_french_status_words(self):
        """Test finding French status words."""
        content = "Télésiège ouvert. Piste fermée. Télécabine en attente."

        result = find_status_indicators(content)

        assert result.status_word_count >= 2
        assert any(m.word in ("ouvert", "ouverte") for m in result.status_matches)
        assert any(m.word in ("fermé", "fermée") for m in result.status_matches)

    def test_german_status_words(self):
        """Test finding German status words."""
        content = "Sessellift geöffnet. Piste geschlossen."

        result = find_status_indicators(content)

        assert result.status_word_count >= 2
        assert any(m.normalized_status == "open" for m in result.status_matches)
        assert any(m.normalized_status == "closed" for m in result.status_matches)

    def test_lift_indicator_words(self):
        """Test counting lift indicator words."""
        content = "The gondola and chairlift are operating. The t-bar is closed."

        result = find_status_indicators(content)

        assert result.lift_indicator_count >= 3

    def test_run_indicator_words(self):
        """Test counting run/piste indicator words."""
        content = "Blue piste is groomed. Black run is closed. The slope is icy."

        result = find_status_indicators(content)

        assert result.run_indicator_count >= 3

    def test_likely_contains_lift_status(self):
        """Test detection of lift status content."""
        content = """
        Lift Status:
        - Gondola: open
        - Chairlift 1: open
        - Chairlift 2: closed
        - T-bar: hold
        """

        result = find_status_indicators(content)

        assert result.likely_contains_lift_status is True
        assert result.lift_indicator_count >= 4

    def test_likely_contains_run_status(self):
        """Test detection of run status content."""
        content = """
        Piste Status:
        - Blue run: open, groomed
        - Red slope: open
        - Black piste: closed
        """

        result = find_status_indicators(content)

        assert result.likely_contains_run_status is True
        assert result.run_indicator_count >= 3

    def test_score_calculation(self):
        """Test that score reflects content relevance."""
        lift_heavy = "gondola chairlift chairlift gondola open closed open closed open"
        no_status = "Welcome to our resort. Book your accommodation today."

        lift_result = find_status_indicators(lift_heavy)
        no_result = find_status_indicators(no_status)

        assert lift_result.score > no_result.score

    def test_status_normalization(self):
        """Test that status words are normalized to English."""
        content = "Télésiège ouvert. Sessellift geöffnet. Lift aperto."

        result = find_status_indicators(content)

        # All should normalize to "open"
        open_matches = [m for m in result.status_matches if m.normalized_status == "open"]
        assert len(open_matches) >= 3

    def test_language_detection(self):
        """Test language detection for status words."""
        content = "ouvert geöffnet aperto abierto"

        result = find_status_indicators(content)

        languages = [m.language for m in result.status_matches]
        assert "french" in languages
        assert "german" in languages
        assert "italian" in languages
        assert "spanish" in languages


class TestAnalyzeResourcesForStatus:
    """Tests for analyze_resources_for_status function."""

    def test_sorts_by_score(self):
        """Test that resources are sorted by relevance score."""
        resources = [
            {
                "url": "https://example.com/about",
                "body": "About our resort. We have great snow.",
            },
            {
                "url": "https://example.com/lifts",
                "body": "Gondola: open. Chair 1: open. Chair 2: closed.",
            },
            {
                "url": "https://example.com/home",
                "body": "Welcome to the resort.",
            },
        ]

        results = analyze_resources_for_status(resources)

        assert len(results) == 3
        assert results[0].resource_url == "https://example.com/lifts"
        assert results[0].score > results[1].score

    def test_empty_resources(self):
        """Test with empty resources."""
        results = analyze_resources_for_status([])

        assert len(results) == 0


class TestStatusConstants:
    """Tests for status word constants."""

    def test_lift_indicators_not_empty(self):
        """Test that lift indicators set is populated."""
        assert len(LIFT_INDICATOR_WORDS) > 20

    def test_run_indicators_not_empty(self):
        """Test that run indicators set is populated."""
        assert len(RUN_INDICATOR_WORDS) > 5

    def test_status_words_mapping(self):
        """Test that status words map to valid normalized values."""
        valid_statuses = {"open", "closed", "hold", "wind_hold", "scheduled", "groomed"}

        for source, normalized in STATUS_WORDS.items():
            assert normalized in valid_statuses, f"{source} maps to invalid status {normalized}"
