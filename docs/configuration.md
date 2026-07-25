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
  rag_relevance_min: 0.15
  intent_override: null
  intent_detection_window: 4
```

| Field | Default | What it does |
|-------|---------|---------------|
| `level` | `balanced` | `conservative`, `balanced`, or `aggressive`. Controls how hard each strategy compresses. |
| `quality_threshold` | `72` | Predicted quality score (0-100) below which the original, uncompressed payload is sent instead. |
| `history_window` | `6` | Number of most recent conversation turns kept verbatim; older turns are summarized. |
| `rag_relevance_min` | `0.15` | TF-IDF relevance score below which a RAG chunk is dropped. |
| `intent_override` | `null` | Force `debug`, `build`, `explore`, `refactor`, or `unknown` instead of auto-detecting. Env override: `CONTEXTPILOT_INTENT`. |
| `intent_detection_window` | `4` | How many recent turns the intent heuristic looks at when auto-detecting. |

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
