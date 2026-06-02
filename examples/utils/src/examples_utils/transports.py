"""HTTP transports for TLS-incompatible endpoints.

Provides two transport backends for httpx:

- **Subprocess curl** (``CurlSubprocessTransport`` / ``AsyncCurlSubprocessTransport``):
  Shells out to ``/usr/bin/curl`` for every request.  Zero extra pip
  dependencies — only requires ``httpx`` and the system ``curl`` binary.
  Used when Python's SSL backends (stdlib ssl, httpx, curl_cffi) cannot
  complete the TLS handshake.

- **curl_cffi** (``CurlCffiTransport`` / ``AsyncCurlCffiTransport``):
  Backed by the ``curl_cffi`` library.  Requires ``pip install curl-cffi``.
  Lighter-weight than subprocess curl but needs the extra dependency.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

# ── Subprocess-curl helpers ──────────────────────────────────────────────────


def parse_header_file(raw: bytes) -> tuple[int, httpx.Headers]:
    """Parse ``curl -D`` output into ``(status_code, headers)``.

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


def build_curl_args(
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


# ── Subprocess-curl transports ───────────────────────────────────────────────


class CurlSubprocessTransport(httpx.BaseTransport):
    """Sync httpx transport that delegates HTTP requests to ``/usr/bin/curl``."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Execute the request via /usr/bin/curl subprocess."""
        method = request.method if isinstance(request.method, str) else request.method.decode()
        url = str(request.url)
        t0 = time.time()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".body") as bf, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".hdr") as hf:
            body_path, header_path = bf.name, hf.name
        try:
            cmd = build_curl_args(request, body_path, header_path)
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
                parsed_status, resp_headers = parse_header_file(header_raw)
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


class AsyncCurlSubprocessTransport(httpx.AsyncBaseTransport):
    """Async httpx transport that delegates HTTP requests to ``/usr/bin/curl``."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Execute the request asynchronously via /usr/bin/curl subprocess."""
        method = request.method if isinstance(request.method, str) else request.method.decode()
        url = str(request.url)
        t0 = time.time()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".body") as bf, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".hdr") as hf:
            body_path, header_path = bf.name, hf.name
        try:
            cmd = build_curl_args(request, body_path, header_path)
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
                parsed_status, resp_headers = parse_header_file(header_raw)
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


# ── curl_cffi transports (optional dependency) ────────────────────────────────

try:
    from curl_cffi import requests as _curl_requests
    from curl_cffi.requests import AsyncSession as _CurlAsyncSession

    class CurlCffiTransport(httpx.BaseTransport):
        """httpx transport backed by ``curl_cffi`` to handle TLS-incompatible endpoints."""

        _session = _curl_requests.Session()

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            """Execute the request via curl_cffi."""
            method = request.method if isinstance(request.method, str) else request.method.decode()
            headers = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in request.headers.items()
            }
            resp = self._session.request(
                method=method,
                url=str(request.url),
                headers=headers,
                data=request.content,
                timeout=30,
            )
            return httpx.Response(
                status_code=resp.status_code,
                headers=httpx.Headers(resp.headers),
                content=resp.content,
                request=request,
            )

    class AsyncCurlCffiTransport(httpx.AsyncBaseTransport):
        """Async httpx transport backed by ``curl_cffi``."""

        _session = _CurlAsyncSession()

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            """Execute the request asynchronously via curl_cffi."""
            method = request.method if isinstance(request.method, str) else request.method.decode()
            headers = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in request.headers.items()
            }
            resp = await self._session.request(
                method=method,
                url=str(request.url),
                headers=headers,
                data=request.content,
                timeout=30,
            )
            return httpx.Response(
                status_code=resp.status_code,
                headers=httpx.Headers(resp.headers),
                content=resp.content,
                request=request,
            )

except ImportError:

    class CurlCffiTransport(httpx.BaseTransport):  # type: ignore[no-redef]
        """Stub — ``curl_cffi`` is not installed."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Raise ImportError — curl_cffi is not installed."""
            raise ImportError(
                "curl_cffi is required for CurlCffiTransport. "
                "Install it with: pip install curl-cffi"
            )

    class AsyncCurlCffiTransport(httpx.AsyncBaseTransport):  # type: ignore[no-redef]
        """Stub — ``curl_cffi`` is not installed."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Raise ImportError — curl_cffi is not installed."""
            raise ImportError(
                "curl_cffi is required for AsyncCurlCffiTransport. "
                "Install it with: pip install curl-cffi"
            )
