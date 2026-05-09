from __future__ import annotations

import re
from contextpilot.config import ContextPilotConfig

# Markers that LangChain / CrewAI / AutoGen insert in chain-of-thought output
_SCAFFOLDING = re.compile(
    r"(?:Thought:|Action:|Observation:|> Entering|> Finished|"
    r"AgentAction\(|AgentFinish\(|ToolInvocation\()",
    re.IGNORECASE,
)


def compress_agent_handoff(
    agent_output: str,
    preserve_keys: list[str] | None = None,
    config: ContextPilotConfig | None = None,
) -> str:
    """FR-008: Compress inter-agent context handoff.

    Strips internal agent scaffolding (chain-of-thought markers, tool logs)
    and summarises narrative reasoning into key-point format. Structured
    outputs matching preserve_keys pass through unchanged.

    Target: 70–90% reduction in inter-agent context transfer
    (technical doc §3.5).
    """
    if not agent_output:
        return agent_output

    lines = agent_output.splitlines()
    preserved: list[str] = []
    narrative: list[str] = []
    decisions: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Keep lines containing preserve_keys verbatim
        if preserve_keys and any(k.lower() in stripped.lower() for k in preserve_keys):
            preserved.append(stripped)
            continue

        # Drop scaffolding lines
        if _SCAFFOLDING.search(stripped):
            continue

        # Heuristic: short decisive lines → likely a decision/output
        if len(stripped) < 120 and stripped.endswith((".", ":", "!")):
            decisions.append(stripped)
        else:
            narrative.append(stripped)

    # Summarise narrative: keep first sentence of each paragraph
    summary_parts: list[str] = []
    if narrative:
        for para in " ".join(narrative).split("  "):
            first_sentence = re.split(r"(?<=[.!?])\s", para.strip())[0]
            if first_sentence:
                summary_parts.append(first_sentence)

    parts: list[str] = []
    if preserved:
        parts.append("[KEY OUTPUTS]\n" + "\n".join(f"• {p}" for p in preserved))
    if decisions:
        parts.append("[DECISIONS]\n" + "\n".join(f"• {d}" for d in decisions))
    if summary_parts:
        parts.append("[SUMMARY]\n" + "\n".join(f"• {s}" for s in summary_parts[:5]))

    return "\n\n".join(parts) if parts else agent_output
