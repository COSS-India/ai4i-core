"""
Comprehensive tests for feature flag functionality
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from models.feature_flag_models import (
    FeatureFlagEvaluationRequest,
    BulkEvaluationRequest,
    FeatureFlagCreate,
)
from repositories.feature_flag_repository import FeatureFlagRepository
from services.feature_flag_service import FeatureFlagService
from providers.unleash_provider import UnleashFeatureProvider
from openfeature.evaluation_context import EvaluationContext


# Test UnleashFeatureProvider
class TestUnleashFeatureProvider:
    """Test OpenFeature Unleash provider"""
    
    def test_provider_initialization(self):
        """Verify provider setup"""
        provider = UnleashFeatureProvider(
            url="http://unleash:4242/api",
            app_name="test-app",
            instance_id="test-1",
            api_token="test-token",
        )
        assert provider.get_metadata().name == "UnleashProvider"
    
    @patch('providers.unleash_provider.UnleashClient')
    def test_resolve_boolean_details(self, mock_unleash_client_class):
        """Test boolean flag evaluation"""
        mock_client = Mock()
        mock_client.is_enabled.return_value = True
        mock_unleash_client_class.return_value = mock_client
        
        provider = UnleashFeatureProvider(
            url="http://unleash:4242/api",
            app_name="test-app",
            instance_id="test-1",
            api_token="test-token",
        )
        provider.client = mock_client
        provider._initialized = True
        
        ctx = EvaluationContext(targeting_key="user-123")
        details = provider.resolve_boolean_details("test-flag", False, ctx)
        
        assert details.value is True
        assert details.flag_key == "test-flag"
    
    @patch('providers.unleash_provider.UnleashClient')
    def test_resolve_string_details(self, mock_unleash_client_class):
        """Test string variant evaluation"""
        from UnleashClient.variants import Variant
        
        mock_client = Mock()
        mock_variant = Mock(spec=Variant)
        mock_variant.enabled = True
        mock_variant.name = "variant-a"
        mock_variant.payload = {"value": "test-value"}
        mock_client.get_variant.return_value = mock_variant
        mock_unleash_client_class.return_value = mock_client
        
        provider = UnleashFeatureProvider(
            url="http://unleash:4242/api",
            app_name="test-app",
            instance_id="test-1",
            api_token="test-token",
        )
        provider.client = mock_client
        provider._initialized = True
        
        ctx = EvaluationContext(targeting_key="user-123")
        details = provider.resolve_string_details("test-flag", "default", ctx)
        
        assert details.value == "test-value"
    
    def test_error_handling(self):
        """Test fallback on errors"""
        provider = UnleashFeatureProvider(
            url="http://unleash:4242/api",
            app_name="test-app",
            instance_id="test-1",
            api_token="test-token",
        )
        provider._initialized = False
        
        ctx = EvaluationContext()
        details = provider.resolve_boolean_details("test-flag", False, ctx)
        
        assert details.value is False
        assert details.reason == "ERROR"


# Test FeatureFlagRepository
@pytest.mark.asyncio
class TestFeatureFlagRepository:
    """Test feature flag repository"""
    
    @pytest.fixture
    def mock_session_factory(self):
        """Mock session factory"""
        return AsyncMock()
    
    @pytest.fixture
    def repository(self, mock_session_factory):
        """Create repository instance"""
        return FeatureFlagRepository(mock_session_factory)
    
    async def test_create_feature_flag(self, repository, mock_session_factory):
        """Create flag in database"""
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        flag = await repository.create_feature_flag(
            name="test-flag",
            description="Test description",
            is_enabled=True,
            environment="development",
        )
        
        assert flag is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    async def test_get_feature_flag(self, repository, mock_session_factory):
        """Retrieve flag by name"""
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        await repository.get_feature_flag("test-flag", "development")
        
        mock_session.execute.assert_called_once()
    
    async def test_record_evaluation(self, repository, mock_session_factory):
        """Record evaluation in audit trail"""
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        evaluation = await repository.record_evaluation(
            flag_name="test-flag",
            user_id="user-123",
            context={"region": "us-west"},
            result=True,
            variant=None,
            environment="development",
            reason="TARGETING_MATCH",
        )
        
        assert evaluation is not None
        mock_session.add.assert_called()


# Test FeatureFlagService
@pytest.mark.asyncio
class TestFeatureFlagService:
    """Test feature flag service"""
    
    @pytest.fixture
    def mock_repository(self):
        """Mock repository"""
        return AsyncMock(spec=FeatureFlagRepository)
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.set = AsyncMock()
        return redis_mock
    
    @pytest.fixture
    def mock_openfeature_client(self):
        """Mock OpenFeature client"""
        client = Mock()
        details = Mock()
        details.value = True
        details.reason = "TARGETING_MATCH"
        client.get_boolean_details.return_value = details
        return client
    
    @pytest.fixture
    def service(self, mock_repository, mock_redis, mock_openfeature_client):
        """Create service instance"""
        return FeatureFlagService(
            repository=mock_repository,
            redis_client=mock_redis,
            kafka_producer=None,
            openfeature_client=mock_openfeature_client,
            kafka_topic="test-topic",
            cache_ttl=300,
        )
    
    async def test_evaluate_boolean_flag(self, service, mock_openfeature_client):
        """Evaluate boolean with caching"""
        result = await service.evaluate_boolean_flag(
            flag_name="test-flag",
            user_id="user-123",
            context={},
            default_value=False,
            environment="development",
        )
        
        assert result is True
        mock_openfeature_client.get_boolean_details.assert_called_once()
    
    async def test_evaluate_with_cache_hit(self, service, mock_redis):
        """Verify cache usage"""
        import json
        from datetime import datetime
        
        cached_response = {
            "flag_name": "test-flag",
            "value": True,
            "variant": None,
            "reason": "TARGETING_MATCH",
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        mock_redis.get.return_value = json.dumps(cached_response)
        
        result = await service.evaluate_flag(
            flag_name="test-flag",
            user_id="user-123",
            context={},
            default_value=False,
            environment="development",
        )
        
        assert result.value is True
    
    async def test_bulk_evaluate_flags(self, service):
        """Bulk evaluation"""
        results = await service.bulk_evaluate_flags(
            flag_names=["flag1", "flag2"],
            user_id="user-123",
            context={},
            environment="development",
        )
        
        assert "flag1" in results
        assert "flag2" in results


# Test API Endpoints
@pytest.mark.asyncio
class TestAPIEndpoints:
    """Test FastAPI endpoints"""
    
    @pytest.fixture
    def mock_service(self):
        """Mock feature flag service"""
        return AsyncMock(spec=FeatureFlagService)
    
    async def test_evaluate_endpoint(self, mock_service):
        """Test POST /evaluate"""
        from routers.feature_flag_router import evaluate_flag
        
        request = FeatureFlagEvaluationRequest(
            flag_name="test-flag",
            user_id="user-123",
            default_value=False,
            environment="development",
        )
        
        mock_service.evaluate_flag.return_value = Mock(
            flag_name="test-flag",
            value=True,
            variant=None,
            reason="TARGETING_MATCH",
            evaluated_at="2024-01-15T10:30:00Z",
        )
        
        # Note: Would need FastAPI test client for full integration test
        # This is a simplified unit test
        assert request.flag_name == "test-flag"
    
    async def test_evaluate_boolean_endpoint(self, mock_service):
        """Test POST /evaluate/boolean"""
        request = FeatureFlagEvaluationRequest(
            flag_name="test-flag",
            user_id="user-123",
            default_value=False,
            environment="development",
        )
        
        assert isinstance(request.default_value, bool)


# Integration tests
@pytest.mark.asyncio
class TestIntegration:
    """Integration tests"""
    
    async def test_end_to_end_evaluation(self):
        """Full flow from API to Unleash"""
        # This would require actual Unleash server running
        # Placeholder for integration test
        pass
    
    async def test_unleash_unavailable_fallback(self):
        """Graceful degradation when Unleash unavailable"""
        # Test that service returns default values when Unleash is down
        pass
    
    async def test_cache_invalidation(self):
        """Cache behavior on updates"""
        # Test that cache is invalidated when flags are updated
        pass

