"""LLM Provider factory for Smart Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    LLM_NONE,
    LLM_OPENAI,
    LLM_ANTHROPIC,
    LLM_OLLAMA,
    LLM_HA_CONVERSATION,
)
from .base import LLMProvider, LLMResponse
from .none_provider import NoneProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from .ha_conversation import HAConversationProvider

__all__ = ["LLMProvider", "LLMResponse", "create_provider"]


def create_provider(
    provider_type: str,
    config: dict[str, Any],
    hass: HomeAssistant | None = None,
) -> LLMProvider:
    """Create the appropriate LLM provider.

    Args:
        provider_type: One of the LLM_* constants
        config: Provider-specific config (api_key, model, url, etc.)
        hass: HomeAssistant instance (required for HA Conversation)

    Returns:
        LLMProvider instance
    """
    if provider_type == LLM_OPENAI:
        return OpenAIProvider(config)
    elif provider_type == LLM_ANTHROPIC:
        return AnthropicProvider(config)
    elif provider_type == LLM_OLLAMA:
        return OllamaProvider(config)
    elif provider_type == LLM_HA_CONVERSATION:
        if hass is None:
            raise ValueError("hass is required for HA Conversation provider")
        return HAConversationProvider(config, hass)
    else:
        return NoneProvider(config)
