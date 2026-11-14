"""Create an end-user MCP connection through the customer SDK."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID

from weavz_sdk import WeavzClient, WeavzError


def validate_url(value: str) -> str:
    parsed = urlsplit(value)
    try:
        local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = False
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a URL without credentials, query parameters, or fragments.")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Use HTTPS, or a loopback HTTP URL for a local fixture.")
    return value.rstrip("/")


def configure(
    client: WeavzClient,
    *,
    workspace_id: str,
    end_user_id: str,
    mode: str,
    server_id: str | None = None,
    on_server_created: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Keep one customer's identity attached to the server and access token."""
    UUID(workspace_id)
    if not end_user_id.strip():
        raise ValueError("An end-user external ID from your trusted backend is required.")
    if mode not in {"tools", "code"}:
        raise ValueError("Mode must be tools or code.")
    if server_id:
        UUID(server_id)
        result = client.mcp_servers.get(server_id)
        server = result["server"]
        if server.get("workspaceId") != workspace_id:
            raise ValueError("The MCP server belongs to a different workspace.")
        if server.get("mode") != mode.upper():
            raise ValueError("The server mode differs. Choose the matching server; its mode was not changed.")
        if server.get("authMode") not in {"bearer", "oauth_and_bearer"}:
            raise ValueError("This server does not accept MCP access tokens. Use OAuth or a bearer-enabled server.")
        if server.get("endUserId") not in {None, end_user_id}:
            raise ValueError("The MCP server is attached to another end user.")

    try:
        client.end_users.create(workspace_id=workspace_id, external_id=end_user_id)
    except WeavzError as error:
        if error.status != 409 or error.code != "DUPLICATE":
            raise

    if not server_id:
        created = client.mcp_servers.create(
            name=f"Example agents ({mode})",
            workspace_id=workspace_id,
            mode=mode.upper(),
            auth_mode="bearer",
            end_user_access="restricted",
            end_user_id=end_user_id,
        )
        server_id = created["server"]["id"]
        UUID(server_id)
        if on_server_created:
            on_server_created(server_id)

    scopes = ["mcp:tools"] + (["mcp:code"] if mode == "code" else [])
    access = client.mcp_servers.create_access_token(
        server_id, end_user_id=end_user_id, scopes=scopes, expires_in=3600
    )
    endpoint = validate_url(access["mcpEndpoint"])
    token = access["accessToken"]
    if not isinstance(token, str) or not token.startswith("mcp_") or any(c.isspace() for c in token):
        raise ValueError("The setup response did not contain a valid MCP access token.")
    return {
        "WEAVZ_MCP_URL": endpoint,
        "WEAVZ_MCP_TOKEN": token,
        "WEAVZ_MCP_MODE": mode,
        "WEAVZ_MCP_SERVER_ID": server_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--end-user-id", required=True, help="External ID chosen by your trusted backend")
    parser.add_argument("--mode", choices=["tools", "code"], default="code")
    parser.add_argument("--server-id", help="Reuse a matching server instead of creating one")
    parser.add_argument("--api-url", default="https://platform.weavz.io")
    parser.add_argument("--output", type=Path, default=Path(".env.weavz"))
    args = parser.parse_args()
    key = os.environ.get("WEAVZ_API_KEY", "")
    if not key.startswith("wvz_") or any(c.isspace() for c in key):
        parser.error("Set WEAVZ_API_KEY to a customer API key in your local environment.")

    try:
        api_url = validate_url(args.api_url)
        UUID(args.workspace_id)
        # Reserve a private output file before creating resources. Existing files
        # and symlinks are never followed or overwritten.
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (ValueError, OSError) as error:
        parser.error(str(error))

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            with WeavzClient(api_key=key, base_url=api_url, max_retries=0) as client:
                settings = configure(
                    client, workspace_id=args.workspace_id, end_user_id=args.end_user_id,
                    mode=args.mode, server_id=args.server_id,
                    on_server_created=lambda identifier: print(f"Created MCP server {identifier}. Reuse --server-id {identifier} if token issuance fails."),
                )
            for name, value in settings.items():
                output.write(f"{name}={json.dumps(value)}\n")
    except Exception as error:
        args.output.unlink(missing_ok=True)
        detail = f" ({error.code}, HTTP {error.status})" if isinstance(error, WeavzError) else ""
        print(f"Setup did not finish{detail}. No credentials were printed. Check existing example resources before retrying.")
        return 1
    print(f"Saved private MCP settings to {args.output.name}. The access token expires in one hour.")
    print("Configure app access in the selected workspace, then run the example's live MCP check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
