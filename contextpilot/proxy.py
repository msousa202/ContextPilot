"""FR-009: Local proxy server (Surface B).

Starts an OpenAI-compatible HTTP proxy on localhost that intercepts requests
from AI coding tools (Claude Code, GPT Codex, Aider), compresses the message
payload via the shared pipeline, then forwards to the real provider.

Usage:
    contextpilot proxy --port 8432

Claude Code:
    export ANTHROPIC_BASE_URL=http://localhost:8432

OpenAI SDK / GPT Codex:
    export OPENAI_BASE_URL=http://localhost:8432/v1
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline

log = logging.getLogger(__name__)

try:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response, StreamingResponse
    from starlette.routing import Route
    _STARLETTE_AVAILABLE = True
except ImportError:
    _STARLETTE_AVAILABLE = False

OPENAI_BASE = "https://api.openai.com"
ANTHROPIC_BASE = "https://api.anthropic.com"

_HOP_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
    "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "upgrade",
})


def _forward_headers(request: "Request") -> dict[str, str]:
    return {k: v for k, v in request.headers.items() if k.lower() not in _HOP_HEADERS}


def _detect_provider(request: "Request") -> str:
    if request.headers.get("anthropic-version") or "/v1/messages" in str(request.url.path):
        return "anthropic"
    return "openai"


def _system_as_str(system: object) -> str | None:
    """Normalize Anthropic system field to a plain string.

    Claude Code sends system as a list of content blocks:
      [{"type": "text", "text": "You are ..."}]
    Our pipeline expects a plain string or None.
    """
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts = [b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"]
        return " ".join(parts) if parts else None
    return None


def _make_app(pipeline: Pipeline) -> "Starlette":  # type: ignore[return]

    async def _openai_chat(request: Request) -> Response:
        raw = await request.body()
        target = OPENAI_BASE + str(request.url.path)
        headers = _forward_headers(request)

        forward_json = None
        try:
            body = json.loads(raw)
            messages: list[dict] = body.get("messages", [])
            optimized, _, _ = pipeline.optimize(
                messages, provider="openai", model=body.get("model", "unknown")
            )
            body["messages"] = optimized
            forward_json = body
        except Exception as exc:
            log.debug("OpenAI compression skipped: %s", exc)

        is_stream = _get_stream_flag(raw, forward_json)

        if is_stream:
            return StreamingResponse(
                _stream(target, raw, forward_json, headers),
                media_type="text/event-stream",
            )
        return await _post(target, raw, forward_json, headers)

    async def _anthropic_messages(request: Request) -> Response:
        raw = await request.body()
        target = ANTHROPIC_BASE + str(request.url.path)
        headers = _forward_headers(request)

        forward_json = None
        try:
            body = json.loads(raw)
            messages: list[dict] = body.get("messages", [])
            system_raw = body.get("system")
            system_str = _system_as_str(system_raw)

            optimized_msgs, optimized_sys, _ = pipeline.optimize(
                messages, system=system_str,
                provider="anthropic", model=body.get("model", "unknown"),
            )
            body["messages"] = optimized_msgs
            # Only rewrite system if it was a plain string — leave content-block lists alone
            if optimized_sys is not None and isinstance(system_raw, str):
                body["system"] = optimized_sys
            forward_json = body
        except Exception as exc:
            log.debug("Anthropic compression skipped: %s", exc)

        is_stream = _get_stream_flag(raw, forward_json)

        if is_stream:
            return StreamingResponse(
                _stream(target, raw, forward_json, headers),
                media_type="text/event-stream",
            )
        return await _post(target, raw, forward_json, headers)

    async def _passthrough(request: Request) -> Response:
        provider = _detect_provider(request)
        target_base = ANTHROPIC_BASE if provider == "anthropic" else OPENAI_BASE
        target = target_base + str(request.url.path)
        raw = await request.body()
        headers = _forward_headers(request)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.request(request.method, target, content=raw, headers=headers)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type"),
        )

    routes = [
        Route("/v1/chat/completions", endpoint=_openai_chat, methods=["POST"]),
        Route("/v1/messages", endpoint=_anthropic_messages, methods=["POST"]),
        Route("/{path:path}", endpoint=_passthrough, methods=["GET", "POST", "PUT", "DELETE", "PATCH"]),
    ]
    return Starlette(routes=routes)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_stream_flag(raw: bytes, forward_json: dict | None) -> bool:
    if forward_json is not None:
        return bool(forward_json.get("stream"))
    try:
        return bool(json.loads(raw).get("stream"))
    except Exception:
        return False


async def _stream(
    target: str,
    raw: bytes,
    forward_json: dict | None,
    headers: dict[str, str],
) -> AsyncIterator[bytes]:
    async with httpx.AsyncClient(timeout=120) as client:
        kwargs = {"json": forward_json} if forward_json is not None else {"content": raw}
        async with client.stream("POST", target, headers=headers, **kwargs) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk


async def _post(
    target: str,
    raw: bytes,
    forward_json: dict | None,
    headers: dict[str, str],
) -> Response:
    async with httpx.AsyncClient(timeout=120) as client:
        if forward_json is not None:
            resp = await client.post(target, json=forward_json, headers=headers)
        else:
            resp = await client.post(target, content=raw, headers=headers)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


def run_proxy(host: str = "127.0.0.1", port: int = 8432, config_path: str | None = None) -> None:
    """Start the proxy server. Blocks until interrupted."""
    if not _STARLETTE_AVAILABLE:
        raise RuntimeError(
            "Proxy surface requires extra dependencies.\n"
            "Install with: pip install contextpilot-ai[proxy]"
        )

    config = ContextPilotConfig.load(config_path)
    pipeline = Pipeline(config)
    app = _make_app(pipeline)

    print(f"ContextPilot proxy listening on http://{host}:{port}")
    print(f"  Anthropic / Claude Code  ->  set ANTHROPIC_BASE_URL=http://{host}:{port}")
    print(f"  OpenAI / GPT Codex       ->  set OPENAI_BASE_URL=http://{host}:{port}/v1")
    print("  Press Ctrl+C to stop.")
    uvicorn.run(app, host=host, port=port, log_level="warning")
