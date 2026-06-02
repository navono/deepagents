"""Factory for creating OpenAI-compatible ChatOpenAI instances.

Provides ``create_chat_model()`` — a single entry-point that reads
``LLM_MODEL_NAME``, ``LLM_BASE_URL``, and ``LLM_API_KEY`` from
environment variables and wires in the appropriate custom HTTP transport
for TLS-incompatible endpoints.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

import httpx

from examples_utils.transports import (
    AsyncCurlCffiTransport,
    AsyncCurlSubprocessTransport,
    CurlCffiTransport,
    CurlSubprocessTransport,
)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

TransportType = Literal["subprocess_curl", "curl_cffi"]


def create_chat_model(
    *,
    transport: TransportType = "subprocess_curl",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: object,
) -> ChatOpenAI:
    """Create a ``ChatOpenAI`` instance configured for TLS-incompatible endpoints.

    Reads ``LLM_MODEL_NAME``, ``LLM_BASE_URL``, and ``LLM_API_KEY`` from
    environment variables if not explicitly provided.  Uses custom HTTP
    transports to handle endpoints that Python's SSL backends cannot
    handshake with.

    Args:
        transport: Which transport backend to use.

            - ``"subprocess_curl"`` (default) — shells out to
              ``/usr/bin/curl``.  Zero pip dependencies beyond ``httpx``.
            - ``"curl_cffi"`` — uses the ``curl_cffi`` library (must be
              installed separately).

        model: Model name.  Defaults to ``LLM_MODEL_NAME`` env var or
            ``"gpt-4o"``.
        base_url: API base URL.  Defaults to ``LLM_BASE_URL`` env var.
        api_key: API key.  Defaults to ``LLM_API_KEY`` env var.
        temperature: Sampling temperature.  Pass ``None`` to use the model
            default.
        max_tokens: Maximum tokens in the response.  Pass ``None`` for no
            limit.
        **kwargs: Additional keyword arguments forwarded to
            ``ChatOpenAI``.

    Returns:
        A configured ``ChatOpenAI`` instance with custom sync and async
        HTTP clients.

    Raises:
        ImportError: If *transport* is ``"curl_cffi"`` and ``curl_cffi``
            is not installed.
    """
    # Defer import so the module loads even without langchain_openai in
    # some contexts (e.g. type-checking).
    from langchain_openai import ChatOpenAI  # noqa: F811

    if transport == "subprocess_curl":
        sync_transport: httpx.BaseTransport = CurlSubprocessTransport()
        async_transport: httpx.AsyncBaseTransport = AsyncCurlSubprocessTransport()
    elif transport == "curl_cffi":
        sync_transport = CurlCffiTransport()  # raises ImportError if unavailable
        async_transport = AsyncCurlCffiTransport()
    else:
        raise ValueError(
            f"Unknown transport: {transport!r}. Use 'subprocess_curl' or 'curl_cffi'."
        )

    chat_kwargs: dict = {
        "model": model or os.environ.get("LLM_MODEL_NAME", "gpt-4o"),
        "base_url": base_url or os.environ.get("LLM_BASE_URL") or None,
        "api_key": api_key or os.environ.get("LLM_API_KEY"),
        "http_client": httpx.Client(transport=sync_transport),
        "http_async_client": httpx.AsyncClient(transport=async_transport),
    }

    # Only set temperature/max_tokens if explicitly provided, allowing
    # callers to opt into the ChatOpenAI defaults.
    if temperature is not None:
        chat_kwargs["temperature"] = temperature
    if max_tokens is not None:
        chat_kwargs["max_tokens"] = max_tokens

    # Forward any extra kwargs (e.g. default_headers, default_query, etc.)
    chat_kwargs.update(kwargs)

    return ChatOpenAI(**chat_kwargs)
