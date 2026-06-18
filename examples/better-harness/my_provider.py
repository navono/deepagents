"""Register a custom ProviderProfile for non-OpenAI LLM services.

This module registers a "my-provider" provider profile that injects
base_url and api_key into LangChain's init_chat_model via the Deep Agents
provider profile registry.

Configuration is via environment variables:

    MY_PROVIDER_BASE_URL  — API endpoint (e.g. https://api.deepseek.com/v1)
    MY_PROVIDER_API_KEY   — API key

Usage in experiment.toml:

    [experiment]
    model = "my-provider:deepseek-chat"

    [better_agent]
    model = "my-provider:deepseek-chat"
"""

from __future__ import annotations

import os

from deepagents import ProviderProfile, register_provider_profile

register_provider_profile(
    "my-provider",
    ProviderProfile(
        init_kwargs={
            "base_url": os.environ.get("MY_PROVIDER_BASE_URL", ""),
            "api_key": os.environ.get("MY_PROVIDER_API_KEY", ""),
        },
    ),
)
