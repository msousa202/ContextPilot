# SDK interception layer — re-exports for convenience.
# Provider-specific logic lives in adapters/.
from contextpilot.adapters.anthropic_adapter import AnthropicWrapper
from contextpilot.adapters.openai_adapter import OpenAIWrapper

__all__ = ["OpenAIWrapper", "AnthropicWrapper"]
