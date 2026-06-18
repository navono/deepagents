"""Tool selection eval tests.

Verifies that the custom_tools surface includes all required tools with
the expected signatures. All 3 cases fail at baseline because the initial
custom_tools.py only defines a bare create_task without priority, and has
no search_tasks or categorize_task.
"""

from __future__ import annotations

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "workspace"


def read_surface(path: str) -> str:
    """Read a workspace file's content."""
    return (WORKSPACE_ROOT / path).read_text()


def test_direct_create_task() -> None:
    """create_task tool should accept a priority parameter."""
    tools_content = read_surface("custom_tools.py")
    assert "create_task" in tools_content
    assert "priority" in tools_content


def test_search_tasks_available() -> None:
    """A search_tasks tool should be available."""
    tools_content = read_surface("custom_tools.py")
    assert "search_tasks" in tools_content


def test_categorize_tool_exists() -> None:
    """A categorize_task tool should be available."""
    tools_content = read_surface("custom_tools.py")
    assert "categorize_task" in tools_content
