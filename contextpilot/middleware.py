from __future__ import annotations

from contextpilot.config import ContextPilotConfig
from contextpilot.strategies.agent_memory import compress_agent_handoff


class AgentMemory:
    """FR-008: Agent memory middleware for LangChain / CrewAI / AutoGen.

    Compresses inter-agent context handoffs, targeting 70–90% token reduction
    in agentic workflows (technical doc §3.5).

    Usage:
        from contextpilot.middleware import AgentMemory
        memory = AgentMemory(compression_level="aggressive",
                             preserve_keys=["final_answer", "tool_outputs"])
        compressed = memory.compress_handoff(agent_a_output)
        agent_b_output = agent_b.run(task, context=compressed)
    """

    def __init__(
        self,
        compression_level: str = "balanced",
        preserve_keys: list[str] | None = None,
        config: ContextPilotConfig | None = None,
    ) -> None:
        if config is None:
            cfg_data = {"compression": {"level": compression_level}}
            self._config = ContextPilotConfig.model_validate(cfg_data)
        else:
            self._config = config
        self._preserve_keys = preserve_keys or []

    def compress_handoff(self, agent_output: str) -> str:
        """Compress an agent's output before passing it to the next agent."""
        return compress_agent_handoff(agent_output, self._preserve_keys, self._config)
