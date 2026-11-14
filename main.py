from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_ai import models

from engine import run_workflow
from fixture.harness import FixtureServer


ROOT = Path(__file__).resolve().parent


def live_settings() -> tuple[str, str]:
    url, token = os.getenv("WEAVZ_MCP_URL", ""), os.getenv("WEAVZ_MCP_TOKEN", "")
    if not url or not token:
        raise ValueError("Set WEAVZ_MCP_URL and WEAVZ_MCP_TOKEN from your custom MCP server setup.")
    parsed = urlsplit(url)
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = False
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an MCP URL without embedded credentials or query parameters.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("Use HTTPS for live MCP, or loopback HTTP for a local test server.")
    if token.startswith("wvz_") or any(c.isspace() for c in token):
        raise ValueError("Use an MCP access token, not a Weavz customer REST API key.")
    if parsed.path.rstrip("/") == "/mcp/weavz":
        raise ValueError("The personal connector uses client OAuth. Use your custom server endpoint for this bearer example.")
    return url, token


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run this workflow through PydanticAI and Weavz MCP.")
    parser.add_argument("--fixture", action="store_true", help="Run the real agent and MCP adapter with a deterministic local model and synthetic MCP server")
    parser.add_argument("--mode", choices=["tools", "code"], default=os.getenv("WEAVZ_MCP_MODE", "code"))
    parser.add_argument("--prompt", help="Override the live task prompt")
    parser.add_argument("--inputs", type=Path, help="JSON file with non-secret task inputs")
    args = parser.parse_args()
    if args.fixture and (args.prompt or args.inputs):
        parser.error("Fixture mode uses its fixed synthetic task. Use --prompt or --inputs in live mode.")
    scenario = json.loads((ROOT / "scenario.json").read_text())
    if args.fixture:
        models.ALLOW_MODEL_REQUESTS = False
        with FixtureServer(args.mode) as fixture:
            fixture.reject_bad_token()
            report = await run_workflow(scenario, url=fixture.url, token="local-fixture-token", mode=args.mode, fixture=True)
    else:
        try:
            url, token = live_settings()
        except ValueError as error:
            parser.error(str(error))
        inputs = json.loads(args.inputs.read_text()) if args.inputs else None
        report = await run_workflow(scenario, url=url, token=token, mode=args.mode, model=os.getenv("WEAVZ_MODEL"), prompt=args.prompt, inputs=inputs)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
