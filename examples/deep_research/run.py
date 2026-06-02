"""CLI runner for the Deep Research agent.

Usage:
    uv run python run.py "your research question here"
    uv run python run.py  # interactive mode — type your question at the prompt
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env BEFORE any imports that read env vars (e.g. TavilyClient in tools.py)
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from deepagents.backends.utils import file_data_to_string

from agent import agent


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _print_report(result: dict) -> None:
    """Print the final report and save it to a local file."""
    files = result.get("files", {})
    report_content = None
    report_name = "final_report"

    if "/final_report.md" in files:
        report_content = file_data_to_string(files["/final_report.md"])

    if report_content is None:
        # Fallback: find the longest substantive AI message (the actual report)
        messages = result.get("messages", [])
        best_msg = None
        best_len = 0
        for m in messages:
            content = m.content if isinstance(m.content, str) else ""
            # Look for message with report-like content (has headings or is long)
            if len(content) > best_len and ("#" in content or len(content) > 500):
                best_msg = content
                best_len = len(content)
        if best_msg:
            report_content = best_msg
            report_name = "agent_response"

    if report_content:
        print("\n" + "=" * 80)
        print("📄 Final Report")
        print("=" * 80)
        print(report_content)

        # Save to local file
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{report_name}_{ts}.md"
        output_file.write_text(report_content, encoding="utf-8")
        print(f"\n💾 Report saved to: {output_file}")


# ── Callback handler for live progress ────────────────────────────────────────

from langchain_core.callbacks import BaseCallbackHandler


class _ProgressHandler(BaseCallbackHandler):
    """LangChain callback that prints live progress to stdout."""

    def on_llm_start(self, serialized, prompts, **kwargs):
        name = (serialized or {}).get("name", "llm") or "llm"
        print(f"[{_ts()}] 🤖 LLM call start: {name}", flush=True)

    def on_llm_end(self, response, **kwargs):
        gen = response.generations[0][0] if response.generations else None
        if gen is None:
            return
        msg = gen.message
        tool_calls = getattr(msg, "tool_calls", None) or []
        content = getattr(msg, "content", "")
        if tool_calls:
            for tc in tool_calls:
                args_preview = json.dumps(tc.get("args", {}), ensure_ascii=False)[:200]
                print(f"[{_ts()}] 🔧 Tool call: {tc.get('name', '?')}({args_preview})", flush=True)
        if content:
            preview = content[:150].replace("\n", " ")
            print(f"[{_ts()}] 💬 Response: {preview}…", flush=True)
        print(f"[{_ts()}] 🤖 LLM call end", flush=True)

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = (serialized or {}).get("name", "?") or "?"
        inp = json.dumps(input_str, ensure_ascii=False)[:300]
        print(f"[{_ts()}] 🔧 Tool start: {name} | {inp}", flush=True)

    def on_tool_end(self, output, **kwargs):
        preview = str(output)[:150].replace("\n", " ")
        print(f"[{_ts()}] 🔧 Tool end: {preview}…", flush=True)

    def on_chain_start(self, serialized, inputs, **kwargs):
        name = (serialized or {}).get("name", "") or kwargs.get("name", "")
        if name:
            print(f"[{_ts()}] ▶ START {name}", flush=True)

    def on_chain_end(self, outputs, **kwargs):
        pass

    def on_chain_error(self, error, **kwargs):
        print(f"[{_ts()}] ❌ ERROR: {error}", flush=True)

    def on_tool_error(self, error, **kwargs):
        print(f"[{_ts()}] ❌ Tool error: {error}", flush=True)

    def on_llm_error(self, error, **kwargs):
        print(f"[{_ts()}] ❌ LLM error: {error}", flush=True)


def main() -> None:
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("🔍 Enter your research question: ").strip()
        if not query:
            print("No question provided. Exiting.")
            sys.exit(1)

    print(f"\n🔍 Researching: {query}\n", flush=True)
    start = time.time()

    result = agent.invoke(
        {"messages": [{"role": "user", "content": query}]},
        config={"callbacks": [_ProgressHandler()]},
    )

    elapsed = time.time() - start
    print(f"\n⏱  Completed in {elapsed:.1f}s")

    _print_report(result)


if __name__ == "__main__":
    main()
