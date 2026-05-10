"""5 realistic benchmark scenarios demonstrating real token savings."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from contextpilot.pipeline import Pipeline
from contextpilot.config import ContextPilotConfig


def bench(msgs, system=None, level="balanced", model="gpt-4o", rate=5.00):
    cfg = ContextPilotConfig.load()
    cfg.compression.level = level
    p = Pipeline(cfg)
    _, _, e = p.optimize(msgs, system=system, provider="openai", model=model)
    o, c = e.tokens_input_original, e.tokens_input_compressed
    saved = o - c
    pct = saved / o * 100 if o else 0
    status = "FALLBACK   " if e.fallback_triggered else "COMPRESSED "
    print(f"  {status}  {o:,} -> {c:,} tokens  {pct:.1f}% reduction  "
          f"quality={e.quality_score:.1f}/100  {e.compression_ms:.0f}ms")
    if not e.fallback_triggered and pct > 0:
        daily_before = o / 1_000_000 * rate * 1000
        daily_after  = c / 1_000_000 * rate * 1000
        print(f"             At 1k calls/day: ${daily_before:.2f} -> ${daily_after:.2f}  "
              f"(save ${daily_before - daily_after:.2f}/day, "
              f"${(daily_before - daily_after) * 30:.0f}/mo)")
    return e


# --------------------------------------------------------------------------
# TEST 1: Long repetitive coding session (Claude Code user, same codebase)
# Realistic: each message re-states the project context
# --------------------------------------------------------------------------
print()
print("TEST 1: Long coding session — 15 rounds, same codebase context per turn")
print("-" * 70)
code_ctx = (
    "We are building a Python FastAPI application with PostgreSQL database. "
    "The main models are User, Product, and Order. Authentication uses JWT tokens "
    "stored in Redis. The codebase follows clean architecture with repository pattern. "
)
msgs1 = []
for i in range(15):
    msgs1.append({"role": "user",
                  "content": code_ctx + f"Task {i}: implement the endpoint for operation {i}."})
    msgs1.append({"role": "assistant",
                  "content": code_ctx + f"Here is the implementation for task {i}. "
                              f"def endpoint_{i}(db: Session): return crud.get_item_{i}(db)"})
msgs1.append({"role": "user",
              "content": "Now write comprehensive integration tests for all endpoints."})
bench(msgs1)


# --------------------------------------------------------------------------
# TEST 2: RAG pipeline — same docs prepended every turn (common pattern)
# Realistic: RAG pipeline retrieves same chunks repeatedly
# --------------------------------------------------------------------------
print()
print("TEST 2: RAG chatbot — same retrieved docs prepended on every turn (12 rounds)")
print("-" * 70)
irrelevant = (
    "The history of ancient Rome spans more than a millennium starting from the Tiber. "
    "Byzantine Empire preserved Roman traditions from 4th to 15th century. "
    "Mediterranean diet reduces cardiovascular risk through olive oil and legumes. "
    "Greek philosophy including Stoicism influenced Roman emperors like Marcus Aurelius. "
)
relevant = (
    "FastAPI is a modern Python web framework built on Starlette and Pydantic. "
    "Install with: pip install fastapi uvicorn. Routes use Python decorators. "
    "It auto-generates OpenAPI docs and validates requests via type hints. "
)
msgs2 = []
for i in range(12):
    # Each turn: irrelevant docs + relevant doc + question
    context = irrelevant * 2 + relevant + f" Follow-up question {i}: What about async support?"
    msgs2.append({"role": "user", "content": context})
    msgs2.append({"role": "assistant",
                  "content": f"FastAPI supports async natively via Python async/await. "
                              f"Answer {i}: use async def for route handlers."})
msgs2.append({"role": "user", "content": "How do I deploy FastAPI with uvicorn in production?"})
bench(msgs2)


# --------------------------------------------------------------------------
# TEST 3: Verbose system prompt sent on every call (300-word system prompt)
# Realistic: coding assistant with detailed instructions
# --------------------------------------------------------------------------
print()
print("TEST 3: Verbose system prompt — 300-word prompt, 10 conversation turns")
print("-" * 70)
sys_prompt = (
    "You are a senior software engineer and technical lead with 15 years of experience. "
    "You write clean, well-tested, documented Python code following PEP 8 and PEP 257. "
    "You always consider edge cases, error handling, and performance implications. "
    "You never use global variables. You prefer composition over inheritance. "
    "You always add type hints. You write docstrings for all public functions. "
    "You consider security implications in every implementation decision you make. "
    "You follow the SOLID principles and clean architecture patterns in every project. "
    "You always suggest writing unit tests first. You use pytest for all testing needs. "
    "You prefer async code when dealing with any I/O bound operations whatsoever. "
    "You always explain your reasoning thoroughly and clearly before writing any code. "
    "You review your own code for bugs before submitting. You never skip error handling. "
    "You document all configuration options and environment variables in your code. "
) * 2
code_block = (
    "from fastapi import FastAPI, Depends, HTTPException, status "
    "from jose import JWTError, jwt "
    "from passlib.context import CryptContext "
    "from datetime import datetime, timedelta "
    "from redis import asyncio as aioredis "
    "from slowapi import Limiter "
    "import structlog "
    "logger = structlog.get_logger() "
    "SECRET_KEY = 'your-secret-key-here' "
    "ALGORITHM = 'HS256' "
    "ACCESS_TOKEN_EXPIRE_MINUTES = 30 "
    "async def get_current_user(token: str = Depends(oauth2_scheme)): "
    "    credentials_exception = HTTPException(status_code=401) "
    "    try: payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) "
    "    except JWTError: raise credentials_exception "
    "    return payload "
)
turns = [
    ("Write a JWT authentication middleware for FastAPI including token creation and validation.",
     "Here is a comprehensive JWT middleware implementation: " + code_block),
    ("Add Redis-backed rate limiting to protect all endpoints from abuse.",
     "Updated the middleware with SlowAPI rate limiting backed by Redis: " + code_block),
    ("Now add structured request logging with correlation IDs for distributed tracing.",
     "Added structlog-based logging with correlation ID propagation: " + code_block),
    ("Write comprehensive pytest tests covering authentication, rate limiting, and logging.",
     "Here are the pytest integration tests with fixtures and mocks: " + code_block),
    ("Integrate OpenTelemetry tracing with Jaeger exporter for production observability.",
     "Integrated OpenTelemetry SDK with Jaeger exporter and span propagation: " + code_block),
    ("Refactor into separate modules for each cross-cutting concern.",
     "Refactored into auth.py, rate_limit.py, logging.py, tracing.py modules: " + code_block),
    ("Add a comprehensive health check endpoint verifying all dependencies.",
     "Added /health endpoint checking database, Redis, Jaeger, and auth service: " + code_block),
    ("Document all modules with docstrings and update the OpenAPI descriptions.",
     "Added full docstring coverage and OpenAPI response models to all endpoints: " + code_block),
    ("Add Docker and docker-compose support for local development and production.",
     "Added Dockerfile with multi-stage build and docker-compose with all services: " + code_block),
    ("Perform a final security review of the complete middleware stack.",
     "Security review complete. All OWASP top 10 addressed. Production ready: " + code_block),
]
msgs3 = []
for q, a in turns:
    msgs3.append({"role": "user", "content": q})
    msgs3.append({"role": "assistant", "content": a})
msgs3.append({"role": "user", "content": "Summarize all components for the architecture doc."})
bench(msgs3, system=sys_prompt)


# --------------------------------------------------------------------------
# TEST 4: Multi-agent pipeline — 4 agents passing accumulating context (12 turns)
# Realistic: analysis → fix → test → report pipeline where each agent repeats prior output
# --------------------------------------------------------------------------
print()
print("TEST 4: Multi-agent pipeline — 4-stage pipeline, each agent repeats prior context")
print("-" * 70)
base_report = (
    "Analysis complete. Found 47 Python files with 1203 functions total. "
    "Code quality score 8.2 out of 10. Coverage at 67 percent. "
    "Security issues: numpy 1.21 has CVE-2021-41496, requests 2.25 has CVE-2023-32681. "
    "Type hints missing in 23 files. Three circular imports detected in core module. "
    "Recommendation: update dependencies, add mypy strict, increase coverage to 85 percent. "
)
msgs4 = []
for stage in range(4):
    # Each agent echoes the accumulated report + adds its own output
    ctx = base_report * (stage + 1)
    msgs4.append({"role": "user",
                  "content": ctx + f"Stage {stage} agent: proceed with your task."})
    msgs4.append({"role": "assistant",
                  "content": ctx + f"Stage {stage} completed. Updated report with new findings."})
# Add 4 more rounds of the same pattern
for i in range(4):
    msgs4.append({"role": "user",
                  "content": base_report * 3 + f"Verification round {i}: confirm all fixes applied."})
    msgs4.append({"role": "assistant",
                  "content": base_report * 3 + f"Round {i} verified. All {i+1} checks passed."})
msgs4.append({"role": "user", "content": "Generate the final executive summary report."})
bench(msgs4)


# --------------------------------------------------------------------------
# TEST 5: Tool-heavy agentic session — repeated XML tool outputs over many turns
# Realistic: Claude Code executing bash commands, same output schema each time
# --------------------------------------------------------------------------
print()
print("TEST 5: Agentic tool session — 10 turns of XML tool output + analysis")
print("-" * 70)
tool_schema = (
    "<tool_result>\n"
    "  <command>run_tests</command>\n"
    "  <status>success</status>\n"
    "  <empty_field></empty_field>\n"
    "  <output>All tests passed. Coverage: 87%. Duration: 12.3s.</output>\n"
    "  <metadata></metadata>\n"
    "  <empty_section>   </empty_section>\n"
    "</tool_result>\n\n---\n---\n---\n\n"
)
msgs5 = []
for i in range(10):
    msgs5.append({"role": "user",
                  "content": f"Run test suite iteration {i} and check results.\n" + tool_schema * 3})
    msgs5.append({"role": "assistant",
                  "content": f"Iteration {i}: tests passing with 87% coverage. "
                              f"No regressions detected. Pipeline healthy."})
msgs5.append({"role": "user",
              "content": tool_schema * 2 + "Write the final CI/CD status report."})
bench(msgs5)

print()
