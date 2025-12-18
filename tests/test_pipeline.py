"""Tests for the pipeline orchestrator module."""

import json
import tempfile
from pathlib import Path


from ski_lift_status.scraping.models import (
    DataCategory,
    ExtractionConfig,
    ExtractionType,
    PipelineConfig,
)
from ski_lift_status.scraping.pipeline import (
    StatusPageEntry,
    load_pipeline_config,
    load_status_pages,
    save_pipeline_config,
)


class TestStatusPageEntry:
    """Tests for StatusPageEntry dataclass."""

    def test_create_entry(self):
        """Test creating a status page entry."""
        entry = StatusPageEntry(
            resort_id="test-resort",
            resort_name="Test Resort",
            website_url="https://example.com",
            status_page_url="https://example.com/status",
        )

        assert entry.resort_id == "test-resort"
        assert entry.resort_name == "Test Resort"
        assert entry.website_url == "https://example.com"
        assert entry.status_page_url == "https://example.com/status"


class TestLoadStatusPages:
    """Tests for loading status pages from CSV."""

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file."""
        result = load_status_pages(Path("/nonexistent/path.csv"))
        assert result == []

    def test_load_valid_csv(self):
        """Test loading from valid CSV."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("resort_id,resort_name,website_url,status_page_url\n")
            f.write("test-id,Test Resort,https://example.com,https://example.com/status\n")
            f.flush()

            entries = load_status_pages(Path(f.name))

            assert len(entries) == 1
            assert entries[0].resort_id == "test-id"
            assert entries[0].resort_name == "Test Resort"


class TestSavePipelineConfig:
    """Tests for saving pipeline configs."""

    def test_save_config(self):
        """Test saving a pipeline config."""
        config = PipelineConfig(
            resort_id="test-resort",
            resort_name="Test Resort",
            status_page_url="https://example.com/status",
            extraction_configs=[
                ExtractionConfig(
                    resource_url="https://example.com/api",
                    extraction_type=ExtractionType.JSON_PATH,
                    category=DataCategory.DYNAMIC_STATUS,
                ),
            ],
            lift_coverage=0.8,
            run_coverage=0.6,
            is_validated=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            result_path = save_pipeline_config(config, path)

            assert result_path == path
            assert path.exists()

            # Verify content
            with open(path) as f:
                data = json.load(f)
                assert data["resort_id"] == "test-resort"
                assert data["lift_coverage"] == 0.8


class TestLoadPipelineConfig:
    """Tests for loading pipeline configs."""

    def test_load_nonexistent(self):
        """Test loading nonexistent config."""
        result = load_pipeline_config("nonexistent", Path("/nonexistent/path.json"))
        assert result is None

    def test_load_existing(self):
        """Test loading existing config."""
        config = PipelineConfig(
            resort_id="test-resort",
            resort_name="Test Resort",
            status_page_url="https://example.com/status",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test-resort.json"
            save_pipeline_config(config, path)

            loaded = load_pipeline_config("test-resort", path)

            assert loaded is not None
            assert loaded.resort_id == "test-resort"
            assert loaded.resort_name == "Test Resort"
