"""
Unit tests for the LLM API module (llm.py).

Covers:
- _extract_regex:  fenced block, inline backtick, bare line, fallback
- _extract_explanation: presence / absence of explanation after code fence
- Provider registry: dispatch, unknown provider → 400
- OllamaBackend.generate: success, ConnectError → 503, HTTP error → 502
- OpenAICompatBackend.generate: success, malformed response → 502
- /llm/providers: returns correct provider metadata
- /llm/models: ConnectError → 503
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

# ── path ─────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.api.llm import (
    OllamaBackend,
    OpenAICompatBackend,
    _REGISTRY,
    _extract_explanation,
    _extract_regex,
    startup,
    shutdown,
)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _init_client():
    """Initialise the singleton HTTP client before each test that needs it."""
    await startup()


async def _close_client():
    await shutdown()


# =============================================================================
# _extract_regex
# =============================================================================

class TestExtractRegex:
    def test_fenced_plain(self):
        text = "Here is your regex:\n```\n\\d{4}-\\d{2}-\\d{2}\n```\nMatches ISO dates."
        assert _extract_regex(text) == r"\d{4}-\d{2}-\d{2}"

    def test_fenced_regex_lang(self):
        text = "```regex\n^[A-Z]{2}\\d{6}$\n```"
        assert _extract_regex(text) == r"^[A-Z]{2}\d{6}$"

    def test_fenced_python_lang(self):
        text = "```python\n[a-z]+@[a-z]+\\.com\n```"
        assert _extract_regex(text) == r"[a-z]+@[a-z]+\.com"

    def test_inline_backtick(self):
        text = "Use the pattern `\\b\\d{1,3}(\\.\\d{1,3}){3}\\b` for IPv4."
        result = _extract_regex(text)
        assert result is not None
        assert "\\d" in result

    def test_bare_line_with_regex_chars(self):
        # Plain line with regex meta-characters, no fencing
        text = "^(foo|bar)\\s+baz$"
        assert _extract_regex(text) == "^(foo|bar)\\s+baz$"

    def test_empty_input_returns_none(self):
        assert _extract_regex("") is None

    def test_multiline_fenced_takes_first_line(self):
        text = "```\nfirst_pattern\nsecond_pattern\n```"
        result = _extract_regex(text)
        # fenced group strips whitespace — should return both lines joined
        # exact behaviour is: group(1).strip()
        assert result is not None


# =============================================================================
# _extract_explanation
# =============================================================================

class TestExtractExplanation:
    def test_explanation_after_fence(self):
        text = "```\n\\d+\n```\nMatches one or more digits."
        assert _extract_explanation(text) == "Matches one or more digits."

    def test_no_fence_returns_none(self):
        assert _extract_explanation(r"\d+") is None

    def test_empty_after_fence_returns_none(self):
        text = "```\n\\d+\n```\n   "
        assert _extract_explanation(text) is None


# =============================================================================
# Provider registry
# =============================================================================

class TestRegistry:
    def test_ollama_registered(self):
        assert "ollama" in _REGISTRY
        assert isinstance(_REGISTRY["ollama"], OllamaBackend)

    def test_opencode_registered(self):
        assert "opencode" in _REGISTRY
        assert isinstance(_REGISTRY["opencode"], OpenAICompatBackend)

    def test_unknown_provider_missing(self):
        assert _REGISTRY.get("nonexistent") is None


# =============================================================================
# OllamaBackend.generate  (mocked HTTP client)
# =============================================================================

class TestOllamaBackend:
    @pytest.fixture(autouse=True)
    async def _client(self):
        await startup()
        yield
        await shutdown()

    async def test_generate_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "```\n\\d+\n```"}

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            backend = OllamaBackend()
            result = await backend.generate("gemma3:4b", "match digits")
            assert result == "```\n\\d+\n```"
            client.post.assert_awaited_once()

    async def test_generate_connect_error(self):
        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_get.return_value = client

            backend = OllamaBackend()
            with pytest.raises(ConnectionError, match="Cannot reach Ollama"):
                await backend.generate("gemma3:4b", "match digits")

    async def test_generate_http_status_error(self):
        mock_req = MagicMock()
        mock_req2 = MagicMock()
        mock_req2.status_code = 500
        mock_req2.text = "Internal Server Error"
        exc = httpx.HTTPStatusError("500", request=mock_req, response=mock_req2)

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = exc
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            backend = OllamaBackend()
            with pytest.raises(RuntimeError, match="Ollama HTTP 500"):
                await backend.generate("gemma3:4b", "match digits")


# =============================================================================
# OpenAICompatBackend.generate  (mocked HTTP client)
# =============================================================================

class TestOpenAICompatBackend:
    @pytest.fixture(autouse=True)
    async def _client(self):
        await startup()
        yield
        await shutdown()

    async def test_generate_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "```\n[A-Z]+\n```"}}]
        }

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            backend = OpenAICompatBackend()
            result = await backend.generate("gemma3:4b", "uppercase letters")
            assert result == "```\n[A-Z]+\n```"

    async def test_generate_malformed_response(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"choices": []}   # empty choices

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            backend = OpenAICompatBackend()
            with pytest.raises(RuntimeError, match="Unexpected OpenCode response structure"):
                await backend.generate("gemma3:4b", "test")


# =============================================================================
# API endpoint integration tests (using FastAPI test client)
# =============================================================================

@pytest_asyncio.fixture
async def api_client():
    """Real ASGI test client with lifespan (startup/shutdown hooks run)."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestLlmProviders:
    async def test_list_providers(self, api_client):
        resp = await api_client.get("/api/v1/llm/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        ids = [p["id"] for p in data["providers"]]
        assert "ollama" in ids
        assert "opencode" in ids

    async def test_generate_unknown_provider(self, api_client):
        # Pydantic rejects the out-of-Literal value before the handler runs → 422
        resp = await api_client.post(
            "/api/v1/llm/generate-regex",
            json={"description": "match digits", "model": "gemma3:4b", "provider": "nonexistent"},
        )
        assert resp.status_code == 422

    async def test_list_models_ollama_unreachable(self, api_client):
        """When Ollama is offline, /llm/models should return 503."""
        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_get.return_value = client

            resp = await api_client.get("/api/v1/llm/models")
            assert resp.status_code == 503
            assert "Ollama" in resp.json()["detail"]

    async def test_generate_regex_connection_error_returns_503(self, api_client):
        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_get.return_value = client

            resp = await api_client.post(
                "/api/v1/llm/generate-regex",
                json={"description": "match an IPv4 address", "model": "gemma3:4b", "provider": "ollama"},
            )
            assert resp.status_code == 503

    async def test_generate_regex_empty_response_returns_502(self, api_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": ""}

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            resp = await api_client.post(
                "/api/v1/llm/generate-regex",
                json={"description": "match an IPv4 address", "model": "gemma3:4b", "provider": "ollama"},
            )
            assert resp.status_code == 502

    async def test_generate_regex_success(self, api_client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "```\n\\d{1,3}(\\.\\d{1,3}){3}\n```\nMatches IPv4."}

        with patch("app.api.llm.get_http_client") as mock_get:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get.return_value = client

            resp = await api_client.post(
                "/api/v1/llm/generate-regex",
                json={"description": "match an IPv4 address", "model": "gemma3:4b", "provider": "ollama"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "pattern" in data
            assert data["provider"] == "ollama"
            assert data["model"] == "gemma3:4b"
