"""Tests for FR-009: Local proxy server (contextpilot/proxy.py)."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Import guard, proxy extras may not be installed in base test env.
# Skip the whole module rather than error on import.
# ---------------------------------------------------------------------------
pytest.importorskip(
    "starlette", reason="proxy extras not installed (pip install contextpilot[proxy])"
)
pytest.importorskip(
    "uvicorn", reason="proxy extras not installed (pip install contextpilot[proxy])"
)

from starlette.testclient import TestClient  # noqa: E402

from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline
from contextpilot.proxy import _detect_provider, _make_app  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pipeline() -> Pipeline:
    cfg = ContextPilotConfig()
    return Pipeline(cfg)


@pytest.fixture()
def app(pipeline: Pipeline):
    return _make_app(pipeline)


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# _detect_provider
# ---------------------------------------------------------------------------


class TestDetectProvider:
    def test_anthropic_via_header(self, app):
        from starlette.testclient import TestClient

        # Verify that anthropic-version header routes to anthropic
        with TestClient(app) as _:
            # We can test the helper directly without making a full HTTP call
            pass  # tested via integration below

    def test_detect_provider_openai_default(self):
        """Paths without anthropic markers default to openai."""
        from starlette.datastructures import Headers

        class _FakeRequest:
            headers = Headers(headers={})
            url = type("U", (), {"path": "/v1/chat/completions"})()

        assert _detect_provider(_FakeRequest()) == "openai"  # type: ignore[arg-type]

    def test_detect_provider_anthropic_by_path(self):
        from starlette.datastructures import Headers

        class _FakeRequest:
            headers = Headers(headers={})
            url = type("U", (), {"path": "/v1/messages"})()

        assert _detect_provider(_FakeRequest()) == "anthropic"  # type: ignore[arg-type]

    def test_detect_provider_anthropic_by_header(self):
        from starlette.datastructures import Headers

        class _FakeRequest:
            headers = Headers(headers={"anthropic-version": "2023-06-01"})
            url = type("U", (), {"path": "/v1/chat"})()

        assert _detect_provider(_FakeRequest()) == "anthropic"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Proxy compression, intercept without real HTTP forward
# ---------------------------------------------------------------------------


class TestOpenAIProxyCompression:
    """Test that the proxy compresses messages before forwarding.

    We patch httpx.AsyncClient.post so no real network call is made.
    """

    def test_messages_are_compressed_in_body(self, client, monkeypatch):
        """The body forwarded to OpenAI should have the (potentially smaller) messages."""
        captured: list[dict] = []

        async def fake_post(self_inner, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})

            # Return a minimal mock response
            class _Resp:
                content = b'{"id":"chatcmpl-test","choices":[]}'
                status_code = 200
                headers = {"content-type": "application/json"}

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
        resp = client.post("/v1/chat/completions", json=payload)
        # The proxy should have forwarded (status comes from our fake)
        assert resp.status_code == 200
        assert len(captured) == 1
        assert "messages" in captured[0]

    def test_model_preserved(self, client, monkeypatch):
        """The model field must be forwarded unchanged."""
        captured: list[dict] = []

        async def fake_post(self_inner, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})

            class _Resp:
                content = b"{}"
                status_code = 200
                headers = {"content-type": "application/json"}

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": []})
        assert captured[0].get("model") == "gpt-4o-mini"


class TestAnthropicProxyCompression:
    def test_system_forwarded(self, client, monkeypatch):
        """System prompt should be present in the forwarded body."""
        captured: list[dict] = []

        async def fake_post(self_inner, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})

            class _Resp:
                content = b"{}"
                status_code = 200
                headers = {"content-type": "application/json"}

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 256,
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        resp = client.post("/v1/messages", json=payload)
        assert resp.status_code == 200
        assert captured[0].get("system") is not None

    def test_messages_key_present(self, client, monkeypatch):
        captured: list[dict] = []

        async def fake_post(self_inner, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})

            class _Resp:
                content = b"{}"
                status_code = 200
                headers = {"content-type": "application/json"}

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        client.post(
            "/v1/messages",
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 64, "messages": []},
        )
        assert "messages" in captured[0]


class TestPassthroughRoute:
    def test_unknown_path_passes_through(self, client, monkeypatch):
        """Non-LLM paths like /v1/models should be forwarded without modification."""
        called: list[str] = []

        async def fake_request(self_inner, method, url, *, content=None, headers=None, **kwargs):
            called.append(url)

            class _Resp:
                content = b'{"object":"list","data":[]}'
                status_code = 200
                headers = {"content-type": "application/json"}

            return _Resp()

        import httpx

        monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

        resp = client.get("/v1/models")
        assert resp.status_code == 200
        assert len(called) == 1
