# Configuration reference

ContextPilot works with zero configuration. Everything below is optional tuning.

## Where config comes from

Three layers, applied in order, each overriding the last:

1. Defaults built into `contextpilot/config.py`
2. A `contextpilot.yaml` (or `contextpilot.yml`) file in your project root, if present
3. Environment variables, if set

Load it explicitly if you need a non-default path or want to inspect what was resolved:

```python
from contextpilot import ContextPilotConfig

cfg = ContextPilotConfig.load("path/to/contextpilot.yaml")
```

`contextpilot.yaml` is in `.gitignore` by default. Copy `contextpilot.yaml.example` to get started.

## compression

```yaml
compression:
  level: balanced
  quality_threshold: 72
  history_window: 6
  history_epoch: 8
  rag_relevance_min: 0.15
  intent_override: null
  intent_detection_window: 4
  cache_aware: true
  assume_cached: true
  inject_cache_control: true
```

| Field | Default | What it does |
|-------|---------|---------------|
| `level` | `balanced` | `conservative`, `balanced`, or `aggressive`. A preset over `history_window` and `rag_relevance_min` (see below). Any field you set explicitly wins over the preset. |
| `quality_threshold` | `72` | Predicted quality score (0-100) below which the original, uncompressed payload is sent instead. |
| `history_window` | `6` | Number of most recent conversation turns kept verbatim; older turns are summarized. Preset by `level`. |
| `history_epoch` | `8` | The summarization boundary only advances in steps of this many turns, so the forwarded payload stays byte-identical between steps and provider prompt caching keeps working. Lower values compress sooner but invalidate the cache more often. |
| `rag_relevance_min` | `0.15` | TF-IDF relevance score below which a RAG chunk is dropped. Preset by `level`. |
| `intent_override` | `null` | Force `debug`, `build`, `explore`, `refactor`, or `unknown` instead of auto-detecting. Env override: `CONTEXTPILOT_INTENT`. |
| `intent_detection_window` | `4` | How many recent turns the intent heuristic looks at when auto-detecting. |
| `cache_aware` | `true` | Refuse compression that would raise the cache-adjusted cost of the request. Turning this off lets the pipeline optimize token count at the possible expense of your actual bill. |
| `assume_cached` | `true` | Which cost model the gate uses. `true` prices the payload as a repeated conversation whose shared prefix is already served from the provider cache at ~0.1x, which is correct for the proxy and wrapper surfaces. `false` prices it as a one-shot request where every token bills at full price, which is correct when prefixes never repeat. `contextpilot.compress()` defaults to one-shot; pass `assume_cached=True` there if you call it repeatedly over a growing conversation. |
| `inject_cache_control` | `true` | Proxy surface only. Adds a `cache_control` breakpoint to a large, stable, plain-string system prompt when the client set none of its own. Payloads that manage their own breakpoints are never touched. |

### What `level` actually changes

| `level` | `history_window` | `rag_relevance_min` |
|---------|------------------|---------------------|
| `conservative` | 10 | 0.05 |
| `balanced` | 6 | 0.15 |
| `aggressive` | 3 | 0.30 |

Because the summarization boundary is quantized to `history_epoch`, a window difference smaller than the epoch may round to the same boundary and produce identical output. That is the deliberate cost of keeping the forwarded prefix cache-stable. Lower `history_epoch` if you want the window to bite sooner and accept more frequent cache invalidation.

Env var overrides: `CONTEXTPILOT_QUALITY_THRESHOLD`, `CONTEXTPILOT_COMPRESSION_LEVEL`, `CONTEXTPILOT_HISTORY_WINDOW`, `CONTEXTPILOT_INTENT`.

## shadow_testing

```yaml
shadow_testing:
  enabled: false
  sample_rate: 0.05
```

Cosine-similarity comparison between compressed and uncompressed responses, meant to validate that compression isn't silently degrading output quality on a sample of real traffic.

Current status: the comparison logic (`shadow.py`) is implemented but not yet called from the default pipeline, so setting `enabled: true` today has no observable effect. Tracked as an open issue; see [limitations.md](limitations.md).

## telemetry

```yaml
telemetry:
  enabled: true
  endpoint: https://api.contextpilot.org/v1/telemetry
  api_key: ${CONTEXTPILOT_API_KEY}
  flush_size: 100
```

| Field | Default | What it does |
|-------|---------|---------------|
| `enabled` | `true` | Whether to write local events at all. Local logging only, no network calls, regardless of this endpoint/api_key below. |
| `endpoint` | `api.contextpilot.org/v1/telemetry` | Reserved for the future hosted dashboard. Not live yet, see below. |
| `api_key` | `null` | Reserved for the future hosted dashboard. Env override: `CONTEXTPILOT_API_KEY`. |
| `flush_size` | `100` | Number of buffered events before attempting a remote flush, once the hosted dashboard exists. |

With `enabled: true` (the default) and no `api_key`, every API call appends one metadata-only line to `~/.contextpilot/events.jsonl` and nothing ever goes over the network. Setting `api_key` today does not send your data anywhere: the hosted endpoint isn't live yet, so there's nothing to connect to. See [limitations.md](limitations.md) and [SECURITY.md](../SECURITY.md) for the full picture.

## Programmatic config

Skip the YAML file entirely and pass a dict or `ContextPilotConfig` directly:

```python
import contextpilot

client = contextpilot.wrap(OpenAI(), config={
    "compression": {"level": "aggressive", "quality_threshold": 80},
})
```
