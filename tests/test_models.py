"""Tests for scraping pipeline models."""


from ski_lift_status.scraping.models import (
    CapturedResource,
    ClassifiedResource,
    DataCategory,
    ExtractionConfig,
    ExtractionType,
    NetworkCapture,
    PipelineConfig,
    PipelineResult,
    ResourceType,
    SchemaField,
    SchemaOverview,
    SourceMapping,
)


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_resource_types_exist(self):
        """Test that all expected resource types exist."""
        assert ResourceType.XHR == "xhr"
        assert ResourceType.JAVASCRIPT == "javascript"
        assert ResourceType.HTML == "html"
        assert ResourceType.JSON == "json"
        assert ResourceType.OTHER == "other"


class TestDataCategory:
    """Tests for DataCategory enum."""

    def test_data_categories_exist(self):
        """Test that all expected data categories exist."""
        assert DataCategory.STATIC_METADATA == "static_metadata"
        assert DataCategory.DYNAMIC_STATUS == "dynamic_status"
        assert DataCategory.MIXED == "mixed"
        assert DataCategory.UNKNOWN == "unknown"


class TestCapturedResource:
    """Tests for CapturedResource model."""

    def test_create_captured_resource(self):
        """Test creating a captured resource."""
        resource = CapturedResource(
            url="https://example.com/api/lifts",
            resource_type=ResourceType.JSON,
            content_type="application/json",
            content='{"lifts": []}',
            size_bytes=14,
            response_status=200,
        )

        assert resource.url == "https://example.com/api/lifts"
        assert resource.resource_type == ResourceType.JSON
        assert resource.content_type == "application/json"
        assert resource.size_bytes == 14
        assert resource.response_status == 200

    def test_default_headers(self):
        """Test that headers default to empty dict."""
        resource = CapturedResource(
            url="https://example.com",
            resource_type=ResourceType.HTML,
            content="<html></html>",
            size_bytes=13,
            response_status=200,
        )

        assert resource.headers == {}


class TestNetworkCapture:
    """Tests for NetworkCapture model."""

    def test_create_network_capture(self):
        """Test creating a network capture."""
        capture = NetworkCapture(
            resort_id="test-resort",
            status_page_url="https://example.com/status",
        )

        assert capture.resort_id == "test-resort"
        assert capture.status_page_url == "https://example.com/status"
        assert capture.resources == []
        assert capture.page_html is None
        assert capture.load_time_ms == 0.0
        assert capture.errors == []


class TestClassifiedResource:
    """Tests for ClassifiedResource model."""

    def test_create_classified_resource(self):
        """Test creating a classified resource."""
        resource = CapturedResource(
            url="https://example.com/api/lifts",
            resource_type=ResourceType.JSON,
            content='{"lifts": []}',
            size_bytes=14,
            response_status=200,
        )

        classified = ClassifiedResource(
            resource=resource,
            category=DataCategory.DYNAMIC_STATUS,
            lift_coverage=0.75,
            run_coverage=0.5,
            matched_lift_names=["Lift A", "Lift B"],
            contains_status_keywords=True,
            confidence_score=0.85,
        )

        assert classified.category == DataCategory.DYNAMIC_STATUS
        assert classified.lift_coverage == 0.75
        assert classified.run_coverage == 0.5
        assert len(classified.matched_lift_names) == 2
        assert classified.contains_status_keywords is True
        assert classified.confidence_score == 0.85


class TestSchemaField:
    """Tests for SchemaField model."""

    def test_create_schema_field(self):
        """Test creating a schema field."""
        field = SchemaField(
            name="liftName",
            field_type="string",
            sample_values=["Gondola 1", "Chair Lift A"],
            is_identifier=False,
            is_status_field=False,
            is_name_field=True,
        )

        assert field.name == "liftName"
        assert field.field_type == "string"
        assert len(field.sample_values) == 2
        assert field.is_name_field is True
        assert field.is_identifier is False


class TestSchemaOverview:
    """Tests for SchemaOverview model."""

    def test_create_schema_overview(self):
        """Test creating a schema overview."""
        overview = SchemaOverview(
            resource_url="https://example.com/api/lifts",
            category=DataCategory.STATIC_METADATA,
            fields=[
                SchemaField(name="name", field_type="string"),
                SchemaField(name="id", field_type="integer"),
            ],
            sample_objects=[{"name": "Lift A", "id": 1}],
            total_objects_count=50,
            root_path="$.lifts",
        )

        assert overview.resource_url == "https://example.com/api/lifts"
        assert overview.category == DataCategory.STATIC_METADATA
        assert len(overview.fields) == 2
        assert len(overview.sample_objects) == 1
        assert overview.total_objects_count == 50
        assert overview.root_path == "$.lifts"


class TestSourceMapping:
    """Tests for SourceMapping model."""

    def test_create_source_mapping(self):
        """Test creating a source mapping."""
        mapping = SourceMapping(
            static_resource_url="https://example.com/api/metadata",
            dynamic_resource_url="https://example.com/api/status",
            join_key_static="lift_id",
            join_key_dynamic="id",
            match_type="exact",
            confidence_score=0.95,
        )

        assert mapping.static_resource_url == "https://example.com/api/metadata"
        assert mapping.dynamic_resource_url == "https://example.com/api/status"
        assert mapping.join_key_static == "lift_id"
        assert mapping.join_key_dynamic == "id"
        assert mapping.match_type == "exact"
        assert mapping.confidence_score == 0.95


class TestExtractionConfig:
    """Tests for ExtractionConfig model."""

    def test_create_extraction_config(self):
        """Test creating an extraction config."""
        config = ExtractionConfig(
            resource_url="https://example.com/api/lifts",
            extraction_type=ExtractionType.JSON_PATH,
            category=DataCategory.DYNAMIC_STATUS,
            root_selector="$.lifts[*]",
            lift_name_selector="$.name",
            lift_status_selector="$.status",
        )

        assert config.resource_url == "https://example.com/api/lifts"
        assert config.extraction_type == ExtractionType.JSON_PATH
        assert config.category == DataCategory.DYNAMIC_STATUS
        assert config.root_selector == "$.lifts[*]"
        assert config.lift_name_selector == "$.name"


class TestPipelineConfig:
    """Tests for PipelineConfig model."""

    def test_create_pipeline_config(self):
        """Test creating a pipeline config."""
        config = PipelineConfig(
            resort_id="test-resort",
            resort_name="Test Resort",
            status_page_url="https://example.com/status",
            lift_coverage=0.8,
            run_coverage=0.6,
            is_validated=True,
        )

        assert config.resort_id == "test-resort"
        assert config.resort_name == "Test Resort"
        assert config.lift_coverage == 0.8
        assert config.run_coverage == 0.6
        assert config.is_validated is True


class TestPipelineResult:
    """Tests for PipelineResult model."""

    def test_create_pipeline_result(self):
        """Test creating a pipeline result."""
        result = PipelineResult(
            resort_id="test-resort",
            success=True,
            lifts_data=[{"name": "Lift A", "status": "open"}],
            runs_data=[{"name": "Run 1", "status": "open"}],
            lift_coverage=0.75,
            run_coverage=0.5,
        )

        assert result.resort_id == "test-resort"
        assert result.success is True
        assert len(result.lifts_data) == 1
        assert len(result.runs_data) == 1
        assert result.lift_coverage == 0.75
        assert result.run_coverage == 0.5
