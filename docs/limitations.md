# Pros, cons, limitations, and what to avoid

An honest assessment, written for anyone deciding whether to adopt ContextPilot, not marketing copy. If something here is out of date, it means the code moved and this didn't; open an issue.

---

## Pros

- **Compression runs in your own process.** Unlike API-based compression services, your prompt content never gets sent to a third party to be compressed. The provider you're already using (OpenAI, Anthropic) is the only place it goes. This is an architectural property, not a policy promise: there's no code path that could send it elsewhere.
- **Fail-safe by design.** If compression would drop predicted quality below threshold, or if anything in the compression step errors, the original uncompressed payload goes out instead. Worst case is no savings, never a degraded response.
- **Four surfaces, one engine.** The library wrapper, local proxy, MCP server, and CLI migration tool all share the same compression pipeline. Most alternatives cover one integration path; this covers a Python call site, a coding-tool proxy, an MCP-connected assistant, and a bulk codebase migration with the same guarantees.
- **Zero required configuration.** Sane defaults out of the box; `contextpilot.yaml` is for tuning, not for getting started.
- **MIT licensed.** No vendor lock-in, fully inspectable, self-hostable forever regardless of what happens to any future hosted offering.

## Cons

- **Heuristic, not learned, compression.** Scoring is TF-IDF based (staleness, redundancy, relevance, density via scikit-learn), not a trained classifier. Tools like Microsoft's LLMLingua-2 use a model trained specifically to judge what's safe to drop, which can be more accurate at the margin, particularly on prose-heavy content. ContextPilot trades some of that accuracy for being lightweight, dependency-light, and fast enough to run inline on every call without a GPU or a model download.
- **Adds latency.** Small, but non-zero, typically single-digit to low double-digit milliseconds per call in our own benchmarks. If you're latency-sensitive at the microsecond level, measure it in your own setup.
- **Local proxy is single-machine by design.** It's meant for a developer's own machine, not as a shared team gateway. Binding it to `0.0.0.0` for shared use means it forwards any request it receives using whatever `Authorization` header the caller supplies; see [SECURITY.md](../SECURITY.md) before doing that.
- **Complements, doesn't replace, other cost levers.** Provider-native prompt caching (Anthropic, OpenAI) reduces cost on repeated prefixes without reducing token count. Coding tools like Claude Code and Codex CLI now do their own session-level context compaction. ContextPilot compresses the payload of each individual API call; it's additive to those, not a substitute, and the savings don't simply stack to 100%.

## Limitations (current, being tracked)

- **Shadow A/B testing isn't wired in yet.** `shadow.py` implements the cosine-similarity comparison, but nothing in the default pipeline calls it. Setting `shadow_testing.enabled: true` in config currently has no effect. Don't rely on it for validation until this is fixed.
- **No Google Vertex AI adapter yet.** Only OpenAI and Anthropic clients are supported by `contextpilot.wrap()` today, despite Vertex being part of the original plan.
- **The 100K-token / 50ms performance budget isn't independently verified at that scale yet.** Our own benchmarks (reproducible via `python benchmarks/benchmark_readme.py`) top out around 20K tokens per conversation. The budget may well hold, it just hasn't been measured and asserted at the size we quote.
- **Multi-modal and structured content blocks get reduced coverage.** Messages with image blocks or Anthropic/OpenAI-style content-block lists (rather than plain strings) aren't fully normalized before analysis yet, so compression may silently skip those specific messages and send them unchanged, falling back to the same fail-safe behavior as any other compression error. Nothing breaks; those messages just don't get smaller yet.
- **Streaming isn't explicitly handled by the library wrapper.** `stream=True` passes through the OpenAI/Anthropic adapters without dedicated handling or tests. The proxy surface does handle streaming explicitly; the library wrapper's behavior with streaming responses hasn't been verified the same way.

## What to avoid

- **Don't enable remote telemetry expecting it to do anything yet.** The hosted dashboard and its ingestion endpoint aren't live. Setting `CONTEXTPILOT_API_KEY` today is a safe no-op, not a data leak, but also not a working feature.
- **Don't expose the local proxy to a network you don't fully trust.** It's a localhost tool by default for a reason.
- **Don't assume this replaces prompt engineering or provider-side caching.** It's a floor under both, most effective when your prompts are already reasonably well structured and you're also using caching where the provider offers it.
- **Don't treat the benchmark numbers as a guarantee for your workload.** They're measured on realistic but synthetic conversation patterns. Run `python benchmarks/benchmark_readme.py` against something closer to your own traffic before sizing expected savings.
- **Don't confuse this with `github.com/EfficientContext/ContextPilot`.** That's a different, unrelated project doing inference-engine-level context optimization for SGLang/vLLM/llama.cpp. Same name, different tool, different authors.

---

See also: [SECURITY.md](../SECURITY.md) for the full data-handling policy, [configuration.md](configuration.md) for every config field, and the open issues on [GitHub](https://github.com/msousa202/ContextPilot/issues) for what's actively being worked on.
