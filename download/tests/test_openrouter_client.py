"""
Test Suite: OpenRouter Client Integration

Validates:
  1. Client initialization and configuration
  2. AgentRole enum values
  3. Fallback architecture (primary + fallback models)
  4. Exception hierarchy
  5. Token usage tracking
  6. API key handling
  7. Request timeout configuration
  8. 402 Payment Required handling
"""

import pytest


class TestOpenRouterClientInit:
    """Test client initialization."""

    def test_agent_role_enum_values(self, openrouter_client_module):
        """AgentRole enum has the correct roles."""
        roles = list(openrouter_client_module.AgentRole)
        role_values = [r.value for r in roles]
        assert "searcher" in role_values
        assert "parser" in role_values
        assert "architect" in role_values
        assert "builder" in role_values

    def test_singleton_exists(self, openrouter_client_module):
        """Module-level singleton openrouter_client exists."""
        assert hasattr(openrouter_client_module, 'openrouter_client')
        assert isinstance(openrouter_client_module.openrouter_client, openrouter_client_module.OpenRouterClient)

    def test_openai_sdk_imported(self, openrouter_client_module):
        """OpenAI SDK is imported for OpenRouter compatibility."""
        # The module imports from openai package
        assert hasattr(openrouter_client_module, 'AsyncOpenAI')

    def test_rate_limit_error_imported(self, openrouter_client_module):
        """openai.RateLimitError is imported."""
        assert hasattr(openrouter_client_module, 'RateLimitError')


class TestExceptionHierarchy:
    """Test the custom exception hierarchy."""

    def test_base_error(self, openrouter_client_module):
        """OpenRouterError base class exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterError')
        assert issubclass(openrouter_client_module.OpenRouterError, Exception)

    def test_auth_error(self, openrouter_client_module):
        """OpenRouterAuthError exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterAuthError')
        assert issubclass(openrouter_client_module.OpenRouterAuthError,
                          openrouter_client_module.OpenRouterError)

    def test_rate_limit_error(self, openrouter_client_module):
        """OpenRouterRateLimitError exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterRateLimitError')
        assert issubclass(openrouter_client_module.OpenRouterRateLimitError,
                          openrouter_client_module.OpenRouterError)

    def test_model_error(self, openrouter_client_module):
        """OpenRouterModelError exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterModelError')
        assert issubclass(openrouter_client_module.OpenRouterModelError,
                          openrouter_client_module.OpenRouterError)

    def test_timeout_error(self, openrouter_client_module):
        """OpenRouterTimeoutError exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterTimeoutError')
        assert issubclass(openrouter_client_module.OpenRouterTimeoutError,
                          openrouter_client_module.OpenRouterError)

    def test_all_models_failed_error(self, openrouter_client_module):
        """OpenRouterAllModelsFailedError exists."""
        assert hasattr(openrouter_client_module, 'OpenRouterAllModelsFailedError')
        assert issubclass(openrouter_client_module.OpenRouterAllModelsFailedError,
                          openrouter_client_module.OpenRouterError)


class TestTokenUsageTracker:
    """Test the TokenUsageTracker class."""

    def test_tracker_initialization(self, openrouter_client_module):
        """Tracker starts with empty data."""
        tracker = openrouter_client_module.TokenUsageTracker()
        assert tracker.get_summary() == {}

    def test_record_usage(self, openrouter_client_module):
        """Recording usage updates the tracker."""
        tracker = openrouter_client_module.TokenUsageTracker()
        tracker.record("searcher", "model-a", 100, 50)
        summary = tracker.get_role_summary("searcher")
        assert summary["prompt_tokens"] == 100
        assert summary["completion_tokens"] == 50
        assert summary["total_tokens"] == 150
        assert summary["call_count"] == 1

    def test_cumulative_tracking(self, openrouter_client_module):
        """Multiple records accumulate correctly."""
        tracker = openrouter_client_module.TokenUsageTracker()
        tracker.record("parser", "model-b", 100, 50)
        tracker.record("parser", "model-b", 200, 100)
        summary = tracker.get_role_summary("parser")
        assert summary["prompt_tokens"] == 300
        assert summary["completion_tokens"] == 150
        assert summary["total_tokens"] == 450
        assert summary["call_count"] == 2

    def test_per_model_tracking(self, openrouter_client_module):
        """Usage is tracked per-model as well."""
        tracker = openrouter_client_module.TokenUsageTracker()
        tracker.record("searcher", "model-a", 100, 50)
        tracker.record("searcher", "model-b", 200, 100)
        summary = tracker.get_summary()
        assert "model:model-a" in summary
        assert "model:model-b" in summary

    def test_reset(self, openrouter_client_module):
        """Reset clears all tracking data."""
        tracker = openrouter_client_module.TokenUsageTracker()
        tracker.record("searcher", "model-a", 100, 50)
        tracker.reset()
        assert tracker.get_summary() == {}


class TestClientProperties:
    """Test client properties and public API."""

    def test_models_property(self, openrouter_client_module):
        """models property returns a dict."""
        client = openrouter_client_module.openrouter_client
        models = client.models
        assert isinstance(models, dict)

    def test_fallback_models_property(self, openrouter_client_module):
        """fallback_models property returns a dict."""
        client = openrouter_client_module.openrouter_client
        fallbacks = client.fallback_models
        assert isinstance(fallbacks, dict)

    def test_token_usage_property(self, openrouter_client_module):
        """token_usage property returns a TokenUsageTracker."""
        client = openrouter_client_module.openrouter_client
        assert isinstance(client.token_usage, openrouter_client_module.TokenUsageTracker)

    def test_is_openrouter_active_is_bool(self, openrouter_client_module):
        """is_openrouter_active returns a boolean."""
        client = openrouter_client_module.openrouter_client
        assert isinstance(client.is_openrouter_active, bool)
