---
name: parallel-work-plan
description: Breaks a task into parallel tracks with dependencies and verification. Use when splitting work across subagents, streams, or developers, or when the user asks how to divide a large task.
disable-model-invocation: true
---

# Parallel work plan

## Output template

```markdown
## Goal
[One sentence]

## Streams
| ID | Scope | Parallel? | Depends on | Done when |
|----|-------|-----------|------------|-----------|

## Contracts (define first)
- Shared types/APIs: ...

## Merge order
1. ...
```

## Guidance

- Maximize parallelism only where files and APIs do not collide.
- Put risky or ambiguous contracts in “define first” before parallel implementation.
