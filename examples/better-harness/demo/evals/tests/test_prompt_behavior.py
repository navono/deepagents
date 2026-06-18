"""Prompt behavior eval tests.

Verifies that the TASK_BOT_PROMPT module attribute contains the expected
policies. Both cases fail at baseline because the initial prompt is just
"You are a task management assistant. Help users with their tasks."
"""

from __future__ import annotations

import task_bot


def test_followup_policy() -> None:
    """Prompt should include a followup/clarification policy for vague requests."""
    prompt_lower = task_bot.TASK_BOT_PROMPT.lower()
    assert "followup" in prompt_lower or "clarification" in prompt_lower


def test_priority_levels() -> None:
    """Prompt should define priority levels (high, medium, low)."""
    prompt_lower = task_bot.TASK_BOT_PROMPT.lower()
    assert "high" in prompt_lower
    assert "medium" in prompt_lower or "normal" in prompt_lower
    assert "low" in prompt_lower
