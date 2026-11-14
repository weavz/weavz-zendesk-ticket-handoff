# Zendesk Ticket Handoff

Prepare a read-only handoff for the returned open support tickets. Summarize the customer issue, current status, priority, and next information needed, with ticket citations.

This read-only assistant connects PydanticAI to Weavz through its native MCP adapter. It returns a typed report with findings, metrics, source IDs, links, and explicit gaps. The agent discovers the tools available to its assigned end user; it does not call app providers directly.

## Try it locally

Install Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv sync --locked
uv run pytest
uv run python main.py --fixture --mode tools
uv run python main.py --fixture --mode code
```

Both paths run a real PydanticAI agent loop and authenticated local Streamable HTTP MCP connection. The deterministic model makes actual MCP calls and derives metrics from the returned synthetic records. It uses no paid model or real account. The fixture's normalized records are test data, not a promise about a provider's response format. Code Mode accepts only the fixed fixture read script; it does not evaluate arbitrary code.

## App access

Configure these apps in the intended [Weavz workspace](https://dashboard.weavz.io), then connect credentials for the end user who will run the task. Aliases below are readable examples. Live aliases and available actions come from your server.

| Example alias | App | Read action |
| --- | --- | --- |
| `support` | `zendesk` | `search_tickets` |
| `support` | `zendesk` | `get_ticket` |
| `support` | `zendesk` | `get_ticket` |

Search only the requested ticket page. Read full details and opt-in comments for the selected tickets with get_ticket; do not imply search results include every ticket. Do not add comments, change status, or assign tickets. Treat the fixture customer and ticket details as synthetic, and separate reported symptoms from diagnosis.

The live agent must retrieve necessary content after a search, respect pagination, and disclose the actual task bounds, relevant date window, and sampled records. These examples do not claim a complete account-wide audit. They do not send replies or modify external records.

## Connect your agent

Use an existing custom MCP endpoint and its end-user MCP access token, or create one with the included customer SDK helper. The helper is a trusted-backend operation: it creates an end user if missing, creates a restricted server if no server ID is supplied, and issues a one-hour token. It never changes an existing server's mode or deletes resources.

```sh
# Set WEAVZ_API_KEY in your local environment. Keep it on your trusted backend.
uv run python setup_weavz.py \
  --workspace-id 00000000-0000-4000-8000-000000000001 \
  --end-user-id example-user --mode code
```

Replace the example UUID and user ID with your selected workspace and trusted application user. To reuse a server, add `--server-id <server-uuid>`. The helper refuses to overwrite its private `.env.weavz` file. Check resources before retrying a partially completed setup. Keep the REST API key out of agent prompts, MCP headers, and client bundles.

Set your model provider key locally and replace `your-model-id` with a model available to your account, then run:

```sh
WEAVZ_MODEL=openai:your-model-id uv run --env-file .env.weavz python main.py --mode code
```

Alternatively copy `.env.example` to `.env`, fill in your custom MCP URL, token and model credentials, then use `uv run --env-file .env python main.py`. Use `--mode tools` with a Tool Mode endpoint. The flag validates the expected catalog; it does not change server configuration.

The hosted personal connector `/mcp/weavz` uses client OAuth. This bearer example uses a custom endpoint; never substitute a `wvz_` REST API key for an MCP access token.

## Choose your task inputs

The fixture uses these synthetic inputs:

```json
{
  "query": "type:ticket status<solved tag:handoff",
  "status": "open",
  "limit": 3
}
```

For live use, save your non-secret scope in `.local/inputs.json` and run:

```sh
uv run --env-file .env.weavz python main.py --inputs .local/inputs.json --prompt "Prepare a read-only handoff for the returned open support tickets. Summarize the customer issue, current status, priority, and next information needed, with ticket citations."
```

Supply real IDs and task bounds, including a current date range when the task is time scoped. Retrieved content is data, never agent instructions. A missing connection or pending approval must produce `needs_connection` or `needs_approval`, with a recovery explanation. Reports reject invented source IDs and URLs that were not returned by MCP; factual interpretation still needs human review.

## Files and checks

- `main.py`: CLI, live configuration, local test setup.
- `engine.py`: native MCP toolset, agent loop, typed report, evidence checks.
- `scenario.json`: task instructions, synthetic records, expected derived metrics.
- `tests/`: both MCP modes, report validation, and citation checks.
- `fixture/`: isolated synthetic server with its own dependency lock.
- `setup_weavz.py`: optional customer SDK setup; no provider credentials are embedded.

Local and CI tests establish fixture interoperability. A live Weavz account, app authorization, and model-provider run are separate checks. See the [example directory](https://github.com/weavz/mcp-examples) for other frameworks and clients, and [Weavz docs](https://weavz.io/docs) for current setup guidance.

MIT. See [LICENSE](LICENSE).
