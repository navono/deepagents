"""Skills and middleware eval tests.

Verifies that the skills guide and middleware surfaces are properly configured.
All 3 cases fail at baseline: skills are minimal, middleware is empty.
"""

from __future__ import annotations

from pathlib import Path

import task_bot

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "workspace"


def read_surface(path: str) -> str:
    """Read a workspace file's content."""
    return (WORKSPACE_ROOT / path).read_text()


def test_escalation_rules() -> None:
    """Skills should mention escalation criteria for complex issues."""
    skills = read_surface("skills.md")
    assert "escalat" in skills.lower()


def test_duplicate_detection() -> None:
    """Middleware should handle duplicate task detection."""
    middleware = read_surface("middleware.py")
    assert "duplicate" in middleware.lower()


def test_combined_workflow() -> None:
    """Prompt + tools + skills should all be coherent together.

    This scorecard test checks that the three main surfaces have been
    improved consistently: prompt has followup policy, tools include
    search, and skills mention escalation.
    """
    prompt = task_bot.TASK_BOT_PROMPT.lower()
    tools = read_surface("custom_tools.py").lower()
    skills = read_surface("skills.md").lower()

    assert "followup" in prompt or "clarification" in prompt
    assert "search_tasks" in tools
    assert "escalat" in skills
