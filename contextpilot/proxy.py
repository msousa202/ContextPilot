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
from typing import AsyncIterator

import httpx

from contextpilot.config import ContextPilotConfig
from contextpilot.pipeline import Pipeline

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

_HOP_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }
)


def _forward_headers(request: "Request") -> dict[str, str]:
    return {k: v for k, v in request.headers.items() if k.lower() not in _HOP_HEADERS}


def _detect_provider(request: "Request") -> str:
    if request.headers.get("anthropic-version") or "/v1/messages" in str(request.url.path):
        return "anthropic"
    return "openai"


def _make_app(pipeline: Pipeline) -> "Starlette":  # type: ignore[return]

    async def _openai_chat(request: Request) -> Response:
        body = await request.json()
        messages: list[dict] = body.get("messages", [])
        model: str = body.get("model", "unknown")

        optimized, _, _ = pipeline.optimize(messages, provider="openai", model=model)
        body["messages"] = optimized

        target = OPENAI_BASE + str(request.url.path)
        headers = _forward_headers(request)
        is_stream = bool(body.get("stream"))

        if is_stream:
            async def _gen() -> AsyncIterator[bytes]:
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", target, json=body, headers=headers) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

            return StreamingResponse(_gen(), media_type="text/event-stream")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=body, headers=headers)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )

    async def _anthropic_messages(request: Request) -> Response:
        body = await request.json()
        messages: list[dict] = body.get("messages", [])
        system: str | None = body.get("system")
        model: str = body.get("model", "unknown")

        optimized_msgs, optimized_sys, _ = pipeline.optimize(
            messages, system=system, provider="anthropic", model=model
        )
        body["messages"] = optimized_msgs
        if optimized_sys is not None:
            body["system"] = optimized_sys
        elif system is not None:
            body["system"] = system

        target = ANTHROPIC_BASE + str(request.url.path)
        headers = _forward_headers(request)
        is_stream = bool(body.get("stream"))

        if is_stream:
            async def _gen() -> AsyncIterator[bytes]:
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", target, json=body, headers=headers) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk

            return StreamingResponse(_gen(), media_type="text/event-stream")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=body, headers=headers)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )

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


def run_proxy(host: str = "127.0.0.1", port: int = 8432, config_path: str | None = None) -> None:
    """Start the proxy server. Blocks until interrupted."""
    if not _STARLETTE_AVAILABLE:
        raise RuntimeError(
            "Proxy surface requires extra dependencies.\n"
            "Install with: pip install contextpilot[proxy]"
        )

    config = ContextPilotConfig.load(config_path)
    pipeline = Pipeline(config)
    app = _make_app(pipeline)

    print(f"ContextPilot proxy listening on http://{host}:{port}")
    print(f"  Anthropic / Claude Code → export ANTHROPIC_BASE_URL=http://{host}:{port}")
    print(f"  OpenAI / GPT Codex      → export OPENAI_BASE_URL=http://{host}:{port}/v1")
    print("  Press Ctrl+C to stop.")
    uvicorn.run(app, host=host, port=port, log_level="warning")
