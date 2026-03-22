"""Test: LLM provider retry mechanism with exponential backoff."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.base import LLMResponse


class TestRetryMechanism:
    """Verify LiteLLMProvider retry behavior."""

    def setup_method(self):
        self.provider = LiteLLMProvider(
            api_key="test-key",
            api_base="http://localhost:8000",
            default_model="test-model",
        )

    def test_is_retryable_timeout(self):
        """TimeoutError should be retryable."""
        assert self.provider._is_retryable(TimeoutError("timed out"))

    def test_is_retryable_connection_error(self):
        """ConnectionError should be retryable."""
        assert self.provider._is_retryable(ConnectionError("connection refused"))

    def test_is_retryable_os_error(self):
        """OSError should be retryable."""
        assert self.provider._is_retryable(OSError("network unreachable"))

    def test_is_retryable_500_in_message(self):
        """Error message containing '500' should be retryable."""
        assert self.provider._is_retryable(Exception("Internal Server Error 500"))

    def test_is_retryable_502_in_message(self):
        """Error message containing '502' should be retryable."""
        assert self.provider._is_retryable(Exception("Bad Gateway 502"))

    def test_is_retryable_timeout_in_message(self):
        """Error message containing 'timeout' should be retryable."""
        assert self.provider._is_retryable(Exception("Request timeout"))

    def test_not_retryable_auth_error(self):
        """Authentication errors should NOT be retryable."""
        assert not self.provider._is_retryable(Exception("Authentication failed: 401"))

    def test_not_retryable_bad_request(self):
        """400 Bad Request should NOT be retryable."""
        assert not self.provider._is_retryable(Exception("Invalid request format"))

    def test_not_retryable_value_error(self):
        """ValueError should NOT be retryable."""
        assert not self.provider._is_retryable(ValueError("invalid JSON"))

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Successful first call should not trigger any retries."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        with patch("nanobot.providers.litellm_provider.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.return_value = mock_response
            result = await self.provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="test-model",
            )
            assert mock_acomp.call_count == 1
            assert result.content == "Hello!"
            assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_succeed(self):
        """Should retry on timeout and succeed on second attempt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Success after retry"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Request timed out")
            return mock_response

        with patch("nanobot.providers.litellm_provider.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = side_effect
            # Patch asyncio.sleep to skip actual waiting
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await self.provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="test-model",
                )
            assert call_count == 2
            assert result.content == "Success after retry"

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Should return error after max retries exhausted."""
        with patch("nanobot.providers.litellm_provider.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = TimeoutError("always timeout")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await self.provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="test-model",
                )
            # 1 initial + 2 retries = 3 total
            assert mock_acomp.call_count == 3
            assert result.finish_reason == "error"
            assert "always timeout" in result.content

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable(self):
        """Should NOT retry on non-retryable errors (e.g., ValueError)."""
        with patch("nanobot.providers.litellm_provider.acompletion", new_callable=AsyncMock) as mock_acomp:
            mock_acomp.side_effect = ValueError("Invalid argument")
            result = await self.provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="test-model",
            )
            assert mock_acomp.call_count == 1
            assert result.finish_reason == "error"
            assert "Invalid argument" in result.content

    def test_retry_constants(self):
        """Retry constants should have reasonable values."""
        assert LiteLLMProvider._MAX_RETRIES == 2
        assert LiteLLMProvider._RETRY_BASE_DELAY == 1.0
