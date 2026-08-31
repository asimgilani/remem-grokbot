# remem-grokbot

Cursor / Grok Bot plugin that talks to [Remem](https://docs.remem.io) over **MCP stdio**.

This is not a Claude marketplace add. Do not install catalog plugin `53852812` (`remem-memory`). Do not install `asimgilani/remem-memory` (Claude/Codex Mac). Do not point Grok Bot at `https://mcp.remem.io`.

## Install (Cursor / Grok Bot)

Grok Bot connectors are Cursor MCP **stdio** on the shared computer.

1. Install this repo as a Cursor plugin (GitHub: `asimgilani/remem-grokbot`, or a local checkout).
2. Open plugin setup and set the secret **`REMEM_API_KEY`** (`vlt_...`).
3. Optional: `REMEM_API_URL` (default `https://api.remem.io`).
4. Optional: `REMEM_DEFAULT_NAMESPACE` (default `grokbot`). The connector will not write `default`.

The server command is system **`python3`** plus `server.py`. There is no `.venv`.

```json
{
  "mcpServers": {
    "remem": {
      "command": "python3",
      "args": ["${PLUGIN_ROOT}/server.py"],
      "env": {
        "REMEM_API_URL": "https://api.remem.io",
        "REMEM_API_KEY": "${REMEM_API_KEY}",
        "REMEM_DEFAULT_NAMESPACE": "grokbot"
      }
    }
  }
}
```

Manual stdio check from a checkout:

```bash
export REMEM_API_KEY=vlt_your_key
export REMEM_API_URL=https://api.remem.io
python3 server.py
```

## Namespace rules (enforced in the connector)

| Direction | Behavior |
| --- | --- |
| Writes (`remem_ingest`, `remem_extract_facts`) | Always `grokbot`. Omitted namespace is injected. Never `default`. |
| Reads (`remem_query` and the other query tools) | If `namespaces` is omitted, send `["default","grokbot"]`. Do not silently search `["*"]`. |

## Tools

| Tool | HTTP |
| --- | --- |
| `remem_query` | `POST /v1/query` |
| `remem_search` | `POST /v1/query` `mode=fast` (not `GET /v1/search`) |
| `remem_summarize` | `POST /v1/query` `mode=rich` `synthesize=true` |
| `remem_get_document` | `GET /v1/documents/{document_id}` |
| `remem_get_document_chunks` | `GET /v1/documents/{document_id}/chunks` |
| `remem_memory_query` | `POST /v1/query` `include_facts=true` |
| `remem_list_entities` | `GET /v1/entities` |
| `remem_get_entity_facts` | `GET /v1/entities/{entity_id}/facts` |
| `remem_extract_facts` | `POST /v1/documents/{document_id}/extract-facts?namespace=grokbot` |
| `remem_ingest` | `POST /v1/documents/ingest` JSON, `Idempotency-Key` |

Auth: `X-API-Key: vlt_...` and `Authorization: Bearer vlt_...`.

## Health

If [https://api.remem.io/health](https://api.remem.io/health) is down, the connector fails loud. Do not invent paths.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Contract tests do not need a key. A live `remem_query` / `remem_ingest` run happens only when `REMEM_API_KEY` is set in the environment.

## /poteto-mode

Cursor Cloud Agents do not always load catalog pstack. This checkout vendors poteto-mode at `.cursor/skills/poteto-mode/SKILL.md` so `/poteto-mode` works from the repo.

## Sources

1. This plugin's contract (README + `server.py`)
2. Live OpenAPI: https://api.remem.io/openapi.json
3. Docs: https://docs.remem.io (`mcp-integration`, `documents`, `querying`, `authentication`, `namespaces`)
