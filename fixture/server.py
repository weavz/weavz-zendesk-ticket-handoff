"""Synthetic MCP contract, not an upstream provider emulator."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server import MCPServer
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from contract import code_for


class BearerOnly:
    def __init__(self, app: ASGIApp, token: str):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            if dict(scope.get("headers", [])).get(b"authorization") != b"Bearer " + self.token:
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app(mode: str, token: str) -> ASGIApp:
    scenario = json.loads((ROOT / "scenario.json").read_text())
    server = MCPServer("Weavz Workflow Fixture", version="0.1.0")
    if mode == "tools":
        for name in dict.fromkeys(step["tool"] for step in scenario["steps"]):
            cases = [step for step in scenario["steps"] if step["tool"] == name]
            keys = list(cases[0]["arguments"])
            if any(set(step["arguments"]) != set(keys) for step in cases):
                raise ValueError("Repeated fixture actions must use the same selected input fields.")
            if any(not key.isidentifier() for key in keys):
                raise ValueError("Fixture argument names must be valid Python identifiers.")

            def result(arguments: dict[str, Any], cases=cases) -> dict[str, Any]:
                for step in cases:
                    if arguments == step["arguments"]:
                        return {"records": step["records"]}
                raise ValueError("Only the documented synthetic arguments are available in this fixture.")

            def annotation(value: Any) -> str:
                if isinstance(value, bool): return "bool"
                if isinstance(value, int): return "int"
                if isinstance(value, float): return "float"
                if isinstance(value, str): return "str"
                if isinstance(value, list): return "list"
                return "dict"

            params = ", ".join(f"{key}: {annotation(cases[0]['arguments'][key])}" for key in keys)
            arguments = ", ".join(f"{key!r}: {key}" for key in keys)
            namespace = {"result": result}
            # Names are validated above; only a fixed function body is compiled.
            exec(compile(f"def invoke({params}) -> dict:\n    return result({{{arguments}}})", "<fixture-contract>", "exec", dont_inherit=True), namespace)
            invoke = namespace["invoke"]
            invoke.__doc__ = f"Read the synthetic records for {name}; selected inputs only."
            server.tool(name=name)(invoke)
    else:
        @server.tool()
        def weavz_search(query: str) -> dict[str, Any]:
            """Discover the aliases used by this synthetic workflow."""
            return {"query": query, "actions": [{"alias": step["alias"], "action": step["action"]} for step in scenario["steps"]]}

        @server.tool()
        def weavz_read_api(aliases: list[str], detail: str = "signatures") -> dict[str, Any]:
            """Inspect the selected synthetic action signatures."""
            if not set(aliases) <= {step["alias"] for step in scenario["steps"]}:
                raise ValueError("Unknown fixture alias.")
            return {"actions": [{"alias": step["alias"], "action": step["action"], "arguments": step["arguments"]} for step in scenario["steps"] if step["alias"] in aliases], "detail": detail}

        @server.tool()
        def weavz_execute(code: str) -> dict[str, Any]:
            """Accept the fixed read-only fixture script; arbitrary code is rejected."""
            if code != code_for(scenario):
                raise ValueError("This fixture only accepts its documented workflow script.")
            return {"steps": [{"step": step["id"], "result": {"records": step["records"]}} for step in scenario["steps"]]}

    app = server.streamable_http_app()
    async def health(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/health":
            await JSONResponse({"status": "ok"})(scope, receive, send)
        else:
            await app(scope, receive, send)
    return BearerOnly(health, token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["tools", "code"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    token = os.environ.get("MCP_TOKEN")
    if not token: raise SystemExit("MCP_TOKEN is required.")
    uvicorn.run(build_app(args.mode, token), host="127.0.0.1", port=args.port, log_level="warning")
