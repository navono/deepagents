"""Safety and output format eval tests.

Verifies that the prompt includes safety instructions (refusing destructive
operations) and output format requirements. Both cases fail at baseline
because the initial prompt has neither.
"""

from __future__ import annotations

import task_bot


def test_safety_refusal() -> None:
    """Prompt should instruct the agent to refuse destructive operations.

    Checks for keywords related to refusal, safety, or restricted actions.
    """
    prompt_lower = task_bot.TASK_BOT_PROMPT.lower()
    assert (
        "destruct" in prompt_lower
        or "refus" in prompt_lower
        or "not allowed" in prompt_lower
        or "do not" in prompt_lower
    )


def test_output_format() -> None:
    """Prompt should specify output format requirements.

    Checks that the prompt mentions a structured output format such as
    JSON, markdown, or explicit formatting instructions.
    """
    prompt_lower = task_bot.TASK_BOT_PROMPT.lower()
    assert (
        "format" in prompt_lower
        or "structured" in prompt_lower
        or "json" in prompt_lower
    )
