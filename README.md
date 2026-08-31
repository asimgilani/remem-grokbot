# remem-grokbot

Grok Bot Remem plugin. Stdio MCP. Ten house `remem_*` tools against `https://api.remem.io`.

This is not the Claude macOS plugin. This is not catalog `53852812`. This is not `https://mcp.remem.io`.

## Install on Grok Bot

1. Install this repo as a Cursor / Grok Bot plugin (`asimgilani/remem-grokbot`).
2. On the connect card, set secret `REMEM_API_KEY` (`vlt_...`).
3. Leave `REMEM_API_URL` at `https://api.remem.io` unless you are pointing at a known Remem host.
4. Leave `REMEM_DEFAULT_NAMESPACE` at `grokbot`. The connector will not write `default`.

Do not run Claude `/plugin marketplace add`. Do not install `asimgilani/remem-memory`.

Spawn is system `python3` (see `mcp.json`). Alternative: `uv run` with the pins in `pyproject.toml`. Never `.venv/bin/python`.

```text
python3 ${PLUGIN_ROOT}/server.py
```

Dependencies: `mcp==1.26.0`, `httpx==0.28.1`. Install them on the Grok Bot box so `python3` can import them:

```bash
python3 -m pip install 'mcp==1.26.0' 'httpx==0.28.1'
```

Or from the plugin root:

```bash
uv run --project . python server.py
```

## Tools

| Tool | HTTP |
| --- | --- |
| `remem_query` | `POST /v1/query` |
| `remem_search` | `POST /v1/query` `mode=fast` (not `GET /v1/search`) |
| `remem_summarize` | `POST /v1/query` `mode=rich`, `synthesize=true`. Arg is `question` |
| `remem_get_document` | `GET /v1/documents/{document_id}` |
| `remem_get_document_chunks` | `GET /v1/documents/{document_id}/chunks` |
| `remem_memory_query` | `POST /v1/query` `include_facts=true` |
| `remem_list_entities` | `GET /v1/entities` |
| `remem_get_entity_facts` | `GET /v1/entities/{entity_id}/facts` |
| `remem_extract_facts` | `POST /v1/documents/{document_id}/extract-facts` |
| `remem_ingest` | `POST /v1/documents/ingest` JSON `content` |

## Namespace policy

- Writes always `grokbot` unless `REMEM_DEFAULT_NAMESPACE` is set and is not `default`.
- Omitted reads send `["default", "grokbot"]`.
- GET namespace params are comma-separated.
- Document and entity ids must be canonical UUIDs.

## Auth

Sends both `Authorization: Bearer vlt_...` and `X-API-Key: vlt_...`. Ingest sends `Idempotency-Key`.

## Shape tests

```bash
python3 -m pip install 'mcp==1.26.0' 'httpx==0.28.1'
python3 -m unittest discover -s tests -v
```

Those tests are not a live Remem pass.

## Live prove

`REMEM_API_KEY` must already be in the process environment. Do not paste a key.

```bash
python3 scripts/prove_live.py
```

That script calls plugin `remem_query` and `remem_ingest` over stdio against `https://api.remem.io`.

## Next

[ASI-8](https://linear.app/devforgeinc/issue/ASI-8/install-on-grok-bot-then-repoint-http-stays-spare) is install on Grok Bot, then repoint. This repo does not install. HTTP `/home/box/lab/remem/query.py` stays a silent spare. ASI-8 is not a merge substitute.
