from __future__ import annotations

from tinycedx.agents.base import Agent

OPERATOR_AGENT = Agent(
    name="operator", role="operator", models=[], can_call=[],
    prompt_version="operator-policy-v1",
)
