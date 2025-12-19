"""Unit tests for the status normalizer module.

Tests the static mapping functionality without LLM calls.
"""

import pytest

from ski_lift_status.scraping.status_normalizer import (
    NormalizedStatus,
    normalize_status_static,
    normalize_status_sync,
    get_known_mappings,
    add_custom_mapping,
    KNOWN_STATUS_MAPPINGS,
)


class TestNormalizedStatusEnum:
    """Tests for the NormalizedStatus enum."""

    def test_enum_values(self):
        """Test that the enum has the expected values."""
        assert NormalizedStatus.OPEN.value == "open"
        assert NormalizedStatus.CLOSED.value == "closed"
        assert NormalizedStatus.EXPECTED_TO_OPEN.value == "expected_to_open"
        assert NormalizedStatus.NOT_EXPECTED_TO_OPEN.value == "not_expected_to_open"

    def test_enum_is_string(self):
        """Test that enum values are strings."""
        for status in NormalizedStatus:
            assert isinstance(status.value, str)


class TestStaticNormalization:
    """Tests for static status normalization."""

    # English status tests
    @pytest.mark.parametrize("raw_status,expected", [
        ("open", NormalizedStatus.OPEN),
        ("OPEN", NormalizedStatus.OPEN),
        ("Open", NormalizedStatus.OPEN),
        ("opened", NormalizedStatus.OPEN),
        ("operating", NormalizedStatus.OPEN),
        ("running", NormalizedStatus.OPEN),
        ("available", NormalizedStatus.OPEN),
        ("in service", NormalizedStatus.OPEN),
    ])
    def test_english_open_statuses(self, raw_status, expected):
        """Test English open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("closed", NormalizedStatus.CLOSED),
        ("CLOSED", NormalizedStatus.CLOSED),
        ("close", NormalizedStatus.CLOSED),
        ("not operating", NormalizedStatus.CLOSED),
        ("unavailable", NormalizedStatus.CLOSED),
        ("suspended", NormalizedStatus.CLOSED),
        ("maintenance", NormalizedStatus.CLOSED),
        ("wind hold", NormalizedStatus.CLOSED),
    ])
    def test_english_closed_statuses(self, raw_status, expected):
        """Test English closed status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("forecast", NormalizedStatus.EXPECTED_TO_OPEN),
        ("FORECAST", NormalizedStatus.EXPECTED_TO_OPEN),
        ("scheduled", NormalizedStatus.EXPECTED_TO_OPEN),
        ("expected", NormalizedStatus.EXPECTED_TO_OPEN),
        ("waiting", NormalizedStatus.EXPECTED_TO_OPEN),
        ("planned", NormalizedStatus.EXPECTED_TO_OPEN),
    ])
    def test_english_expected_to_open_statuses(self, raw_status, expected):
        """Test English expected_to_open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("out_of_period", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
        ("OUT_OF_PERIOD", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
        ("out of period", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
        ("out of season", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
        ("seasonal closure", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
    ])
    def test_english_not_expected_to_open_statuses(self, raw_status, expected):
        """Test English not_expected_to_open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    # French status tests
    @pytest.mark.parametrize("raw_status,expected", [
        ("ouvert", NormalizedStatus.OPEN),
        ("ouverte", NormalizedStatus.OPEN),
        ("en service", NormalizedStatus.OPEN),
    ])
    def test_french_open_statuses(self, raw_status, expected):
        """Test French open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("fermé", NormalizedStatus.CLOSED),
        ("ferme", NormalizedStatus.CLOSED),
        ("fermée", NormalizedStatus.CLOSED),
        ("hors service", NormalizedStatus.CLOSED),
    ])
    def test_french_closed_statuses(self, raw_status, expected):
        """Test French closed status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("prévu", NormalizedStatus.EXPECTED_TO_OPEN),
        ("prevu", NormalizedStatus.EXPECTED_TO_OPEN),
        ("en attente", NormalizedStatus.EXPECTED_TO_OPEN),
    ])
    def test_french_expected_statuses(self, raw_status, expected):
        """Test French expected_to_open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("hors période", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
        ("hors saison", NormalizedStatus.NOT_EXPECTED_TO_OPEN),
    ])
    def test_french_not_expected_statuses(self, raw_status, expected):
        """Test French not_expected_to_open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    # German status tests
    @pytest.mark.parametrize("raw_status,expected", [
        ("offen", NormalizedStatus.OPEN),
        ("geöffnet", NormalizedStatus.OPEN),
        ("in betrieb", NormalizedStatus.OPEN),
    ])
    def test_german_open_statuses(self, raw_status, expected):
        """Test German open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("geschlossen", NormalizedStatus.CLOSED),
        ("gesperrt", NormalizedStatus.CLOSED),
    ])
    def test_german_closed_statuses(self, raw_status, expected):
        """Test German closed status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    # Italian status tests
    @pytest.mark.parametrize("raw_status,expected", [
        ("aperto", NormalizedStatus.OPEN),
        ("aperta", NormalizedStatus.OPEN),
        ("in funzione", NormalizedStatus.OPEN),
    ])
    def test_italian_open_statuses(self, raw_status, expected):
        """Test Italian open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("chiuso", NormalizedStatus.CLOSED),
        ("chiusa", NormalizedStatus.CLOSED),
    ])
    def test_italian_closed_statuses(self, raw_status, expected):
        """Test Italian closed status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    # Spanish status tests
    @pytest.mark.parametrize("raw_status,expected", [
        ("abierto", NormalizedStatus.OPEN),
        ("abierta", NormalizedStatus.OPEN),
    ])
    def test_spanish_open_statuses(self, raw_status, expected):
        """Test Spanish open status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected

    @pytest.mark.parametrize("raw_status,expected", [
        ("cerrado", NormalizedStatus.CLOSED),
        ("cerrada", NormalizedStatus.CLOSED),
    ])
    def test_spanish_closed_statuses(self, raw_status, expected):
        """Test Spanish closed status strings."""
        result = normalize_status_static(raw_status)
        assert result == expected


class TestEdgeCases:
    """Tests for edge cases and special inputs."""

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = normalize_status_static("")
        assert result is None

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        result = normalize_status_static(None)  # type: ignore
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None."""
        result = normalize_status_static("   ")
        assert result is None

    def test_unknown_status_returns_none(self):
        """Test that unknown status returns None."""
        result = normalize_status_static("unknown_xyz_status")
        assert result is None

    def test_case_insensitivity(self):
        """Test that matching is case insensitive."""
        assert normalize_status_static("OPEN") == NormalizedStatus.OPEN
        assert normalize_status_static("Open") == NormalizedStatus.OPEN
        assert normalize_status_static("oPeN") == NormalizedStatus.OPEN

    def test_whitespace_handling(self):
        """Test that leading/trailing whitespace is handled."""
        assert normalize_status_static("  open  ") == NormalizedStatus.OPEN
        assert normalize_status_static("\topen\n") == NormalizedStatus.OPEN

    def test_underscore_to_space_conversion(self):
        """Test that underscores are converted to spaces."""
        assert normalize_status_static("out_of_period") == NormalizedStatus.NOT_EXPECTED_TO_OPEN
        assert normalize_status_static("OUT_OF_PERIOD") == NormalizedStatus.NOT_EXPECTED_TO_OPEN

    def test_hyphen_to_space_conversion(self):
        """Test that hyphens are converted to spaces."""
        assert normalize_status_static("out-of-period") == NormalizedStatus.NOT_EXPECTED_TO_OPEN


class TestNormalizeStatusSync:
    """Tests for the synchronous normalize_status_sync function."""

    def test_known_status_returns_correct_enum(self):
        """Test that known statuses return the correct enum."""
        assert normalize_status_sync("open") == NormalizedStatus.OPEN
        assert normalize_status_sync("closed") == NormalizedStatus.CLOSED
        assert normalize_status_sync("forecast") == NormalizedStatus.EXPECTED_TO_OPEN

    def test_unknown_status_returns_closed(self):
        """Test that unknown statuses default to CLOSED."""
        assert normalize_status_sync("xyz_unknown") == NormalizedStatus.CLOSED
        assert normalize_status_sync("random_status") == NormalizedStatus.CLOSED

    def test_empty_string_returns_closed(self):
        """Test that empty string returns CLOSED."""
        assert normalize_status_sync("") == NormalizedStatus.CLOSED


class TestCustomMappings:
    """Tests for custom mapping functionality."""

    def test_add_custom_mapping(self):
        """Test adding a custom mapping."""
        # Use a key without underscores since normalize_status_static
        # converts underscores to spaces before lookup
        test_key = "testcustomstatus"
        original_value = KNOWN_STATUS_MAPPINGS.get(test_key)

        try:
            # Add custom mapping
            add_custom_mapping(test_key, NormalizedStatus.OPEN)

            # Verify it works
            result = normalize_status_static(test_key)
            assert result == NormalizedStatus.OPEN
        finally:
            # Restore original state
            if original_value is None:
                KNOWN_STATUS_MAPPINGS.pop(test_key, None)
            else:
                KNOWN_STATUS_MAPPINGS[test_key] = original_value

    def test_get_known_mappings_returns_copy(self):
        """Test that get_known_mappings returns a copy."""
        mappings = get_known_mappings()

        # Verify it's a copy, not the original
        mappings["test_key"] = NormalizedStatus.OPEN  # type: ignore
        assert "test_key" not in KNOWN_STATUS_MAPPINGS


class TestRealWorldStatuses:
    """Tests for real-world status strings from actual resort APIs."""

    @pytest.mark.parametrize("raw_status,expected", [
        # Lumiplan statuses
        ("OPEN", NormalizedStatus.OPEN),
        ("CLOSED", NormalizedStatus.CLOSED),
        ("FORECAST", NormalizedStatus.EXPECTED_TO_OPEN),
        ("OUT_OF_PERIOD", NormalizedStatus.NOT_EXPECTED_TO_OPEN),

        # Skiplan statuses
        ("open", NormalizedStatus.OPEN),
        ("closed", NormalizedStatus.CLOSED),
        ("waiting", NormalizedStatus.EXPECTED_TO_OPEN),
    ])
    def test_real_api_statuses(self, raw_status, expected):
        """Test status strings from real resort APIs."""
        result = normalize_status_static(raw_status)
        assert result == expected


class TestStatusCategories:
    """Tests to ensure correct categorization of statuses."""

    def test_all_open_statuses_map_correctly(self):
        """Test that all known open variants map to OPEN."""
        open_variants = [
            "open", "opened", "operating", "running", "available",
            "ouvert", "offen", "aperto", "abierto"
        ]
        for status in open_variants:
            result = normalize_status_static(status)
            assert result == NormalizedStatus.OPEN, f"'{status}' should be OPEN, got {result}"

    def test_all_closed_statuses_map_correctly(self):
        """Test that all known closed variants map to CLOSED."""
        closed_variants = [
            "closed", "close", "suspended", "maintenance",
            "fermé", "ferme", "geschlossen", "chiuso", "cerrado"
        ]
        for status in closed_variants:
            result = normalize_status_static(status)
            assert result == NormalizedStatus.CLOSED, f"'{status}' should be CLOSED, got {result}"
