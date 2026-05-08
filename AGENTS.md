# Agents overview (Cursor subagents)

**Product/engineering plan**: `Doc/contextpilot_functional_doc.docx`, `Doc/contextpilot_technical_doc.docx`, and `Doc/contextpilot_full_system_architecture.svg`.

Project-defined subagents live in `.cursor/agents/`:

| Agent | Role |
|-------|------|
| `changelog-archivist` | Document what changed (changelog, release notes, commit lines). |
| `structure-guardian` | Refactor and organize code for clarity and stable boundaries. |
| `workstream-coordinator` | Split big tasks into streams for parallel work or delegation. |

See `CLAUDE.md` for usage notes and architecture reference.
