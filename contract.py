"""The fixed local workflow script, shared by the agent test and MCP fixture."""
from __future__ import annotations

import json
from typing import Any


def code_for(scenario: dict[str, Any]) -> str:
    lines, results = [], []
    for index, step in enumerate(scenario["steps"]):
        function = step.get("function", step["action"].replace("-", "_"))
        alias = step["alias"]
        if not alias.isidentifier() or not function.isidentifier():
            raise ValueError("Fixture executable names must be valid identifiers.")
        lines.append(f"const result{index} = await weavz.{alias}.{function}({json.dumps(step['arguments'])});")
        results.append(f"{{step: {json.dumps(step['id'])}, result: result{index}}}")
    return "\n".join(lines + ["return {steps: [" + ", ".join(results) + "]};"])
