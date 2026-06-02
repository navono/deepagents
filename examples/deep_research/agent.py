"""Research Agent - Standalone script for LangGraph deployment.

This module creates a deep research agent with custom tools and prompts
for conducting web research with strategic thinking and context management.
"""

import asyncio
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx
from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from research_agent.prompts import (
    RESEARCH_WORKFLOW_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    SUBAGENT_DELEGATION_INSTRUCTIONS,
)
from research_agent.tools import tavily_search, think_tool

load_dotenv(Path(__file__).parent / ".env")


# ── Subprocess-curl transports for TLS-incompatible endpoints ─────────────────
#
# The MaaS endpoint uses a TLS configuration that Python's SSL backends
# (stdlib ssl, httpx, curl_cffi) cannot handshake with, but the system
# `curl` (OpenSSL 3.0) works fine.  We bridge this by shelling out to
# `/usr/bin/curl` for every request.


def _parse_header_file(raw: bytes) -> tuple[int, httpx.Headers]:
    """Parse curl -D output into (status_code, headers).

    Handles the case where an HTTPS proxy prepends a ``200 Connection
    established`` block — we always take the *last* HTTP status line.
    """
    text = raw.decode("utf-8", errors="replace")
    status_code = 502
    headers_list: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("HTTP/"):
            parts = line.split(" ", 2)
            status_code = int(parts[1]) if len(parts) >= 2 else 502
            headers_list.clear()  # reset headers for the last response block
        elif ":" in line:
            k, _, v = line.partition(":")
            headers_list.append((k.strip(), v.strip()))
    return status_code, httpx.Headers(headers_list)


def _build_curl_args(
    request: httpx.Request,
    body_file: str,
    header_file: str,
) -> list[str]:
    """Build the curl command-line arguments for an httpx request."""
    method = request.method if isinstance(request.method, str) else request.method.decode()
    headers: list[str] = []
    for k, v in request.headers.items():
        hk = k.decode() if isinstance(k, bytes) else k
        hv = v.decode() if isinstance(v, bytes) else v
        # Skip host and content-length; curl sets them automatically
        if hk.lower() in ("host", "content-length"):
            continue
        headers += ["-H", f"{hk}: {hv}"]

    cmd = [
        "curl", "-k", "-s", "--noproxy", "*",
        "-X", method,
        "-o", body_file,
        "-D", header_file,
        "-w", "%{http_code}",
        *headers,
    ]
    if request.content:
        cmd += ["-d", "@-"]
    cmd.append(str(request.url))
    return cmd


class _CurlSubprocessTransport(httpx.BaseTransport):
    """Sync httpx transport that delegates HTTP requests to /usr/bin/curl."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        method = request.method if isinstance(request.method, str) else request.method.decode()
        url = str(request.url)
        t0 = time.time()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".body") as bf, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".hdr") as hf:
            body_path, header_path = bf.name, hf.name
        try:
            cmd = _build_curl_args(request, body_path, header_path)
            proc = subprocess.run(
                cmd,
                input=request.content or None,
                capture_output=True,
                timeout=120,
            )
            status_code = int(proc.stdout.strip()) if proc.stdout.strip() else 502
            header_raw = Path(header_path).read_bytes()
            body = Path(body_path).read_bytes()
            # If -w status and -D header disagree, prefer -D
            if header_raw:
                parsed_status, resp_headers = _parse_header_file(header_raw)
                status_code = parsed_status
            else:
                resp_headers = httpx.Headers()
            elapsed = time.time() - t0
            print(f"[curl] ← {method} {url.split('?')[0]} [{status_code}] {elapsed:.1f}s {len(body)}B", flush=True)
            if status_code >= 400:
                print(f"[curl] ⚠ body: {body[:500].decode(errors='replace')}", flush=True)
            return httpx.Response(
                status_code=status_code,
                headers=resp_headers,
                content=body,
                request=request,
            )
        finally:
            Path(body_path).unlink(missing_ok=True)
            Path(header_path).unlink(missing_ok=True)


class _AsyncCurlSubprocessTransport(httpx.AsyncBaseTransport):
    """Async httpx transport that delegates HTTP requests to /usr/bin/curl."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        method = request.method if isinstance(request.method, str) else request.method.decode()
        url = str(request.url)
        t0 = time.time()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".body") as bf, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".hdr") as hf:
            body_path, header_path = bf.name, hf.name
        try:
            cmd = _build_curl_args(request, body_path, header_path)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if request.content else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate(input=request.content)
            status_code = int(stdout.strip()) if stdout.strip() else 502
            header_raw = Path(header_path).read_bytes()
            body = Path(body_path).read_bytes()
            if header_raw:
                parsed_status, resp_headers = _parse_header_file(header_raw)
                status_code = parsed_status
            else:
                resp_headers = httpx.Headers()
            elapsed = time.time() - t0
            print(f"[curl] ← {method} {url.split('?')[0]} [{status_code}] {elapsed:.1f}s {len(body)}B", flush=True)
            if status_code >= 400:
                print(f"[curl] ⚠ body: {body[:500].decode(errors='replace')}", flush=True)
            return httpx.Response(
                status_code=status_code,
                headers=resp_headers,
                content=body,
                request=request,
            )
        finally:
            Path(body_path).unlink(missing_ok=True)
            Path(header_path).unlink(missing_ok=True)


# Limits
max_concurrent_research_units = 3
max_researcher_iterations = 3

# Get current date
current_date = datetime.now().strftime("%Y-%m-%d")

# Combine orchestrator instructions (RESEARCHER_INSTRUCTIONS only for sub-agents)
INSTRUCTIONS = (
    RESEARCH_WORKFLOW_INSTRUCTIONS
    + "\n\n"
    + "=" * 80
    + "\n\n"
    + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
        max_concurrent_research_units=max_concurrent_research_units,
        max_researcher_iterations=max_researcher_iterations,
    )
)

# Create research sub-agent
research_sub_agent = {
    "name": "research-agent",
    "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
    "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
    "tools": [tavily_search, think_tool],
}

# OpenAI-compatible LLM (configured via LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME)
# Uses subprocess curl transports because Python SSL backends cannot complete
# the TLS handshake with this endpoint, but system curl works fine.
model = ChatOpenAI(
    model=os.environ.get("LLM_MODEL_NAME", "gpt-4o"),
    base_url=os.environ.get("LLM_BASE_URL") or None,
    api_key=os.environ.get("LLM_API_KEY"),
    temperature=0.0,
    max_tokens=131072,
    http_client=httpx.Client(transport=_CurlSubprocessTransport()),
    http_async_client=httpx.AsyncClient(transport=_AsyncCurlSubprocessTransport()),
)

# Create the agent
agent = create_deep_agent(
    model=model,
    tools=[tavily_search, think_tool],
    system_prompt=INSTRUCTIONS,
    subagents=[research_sub_agent],
)
