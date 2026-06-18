"""Agent construction."""


def build_agent(model: str):
    """Build a task assistant agent."""
    from custom_tools import create_task
    from task_bot import TASK_BOT_PROMPT

    return {
        "model": model,
        "tools": [create_task],
        "middleware": [],
        "prompt": TASK_BOT_PROMPT,
    }
