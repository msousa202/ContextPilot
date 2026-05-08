---
name: log-code-changes
description: Produces changelog entries, release notes bullets, and conventional commit lines from git diffs or described work. Use when the user asks to log changes, write CHANGELOG entries, or summarize what changed before commit or release.
disable-model-invocation: true
---

# Log code changes

## Steps

1. Determine scope: staged only (`git diff --cached`), working tree (`git diff`), or branch (`git diff main...HEAD`).
2. Group by concern (feature area, bugfix, refactor). Map files to user-visible outcomes when possible.
3. Output:
   - **Changelog block** (bullets, semver section if applicable).
   - **Commit suggestion**: `type(scope): summary` (Conventional Commits).

## Rules

- Never claim changes not evidenced by diff or explicit user list.
- Prefer linking to issue IDs if the user provides them.
