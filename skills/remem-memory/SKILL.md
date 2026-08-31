---
name: remem-memory
description: Query and write Remem memory for Grok Bot via the house remem_* MCP tools. Prefer reading namespace default, write only grokbot. Use when recalling prior context, ingesting notes, or looking up entities and facts. Never install the macOS Claude remem-memory plugin or catalog 53852812.
---

# Remem memory (Grok Bot)

Use the **ten house MCP tools** from this plugin. Do not call `mem_store` or `mem_recall`. Do not install catalog plugin `53852812`. Do not install `asimgilani/remem-memory` (Claude/Codex Mac plugin). Do not use `https://mcp.remem.io`. Do not `POST /v1/ingest`.

## Fail loud

1. If `GET https://api.remem.io/health` is down or not healthy, stop. Do not invent paths or pretend a write succeeded.
2. If `REMEM_API_KEY` is missing, stop. Ask for the plugin setup secret. Never print the key.
3. If a tool returns `isError`, treat it as failure. Do not retry onto a guessed URL.

## Read

Prefer namespace `default` when you want house/shared memory. The connector also includes `grokbot` when `namespaces` is omitted (`["default","grokbot"]`). Pass an explicit list when you need one namespace only.

| Need | Tool |
| --- | --- |
| Full query (`mode`, filters, facts) | `remem_query` |
| Fast search | `remem_search` (`POST /v1/query` `mode=fast`, not `GET /v1/search`) |
| Synthesized answer | `remem_summarize` (`mode=rich`, `synthesize=true`) |
| Facts / knowledge graph | `remem_memory_query` (`include_facts=true`) |
| One document | `remem_get_document` |
| Chunks | `remem_get_document_chunks` |
| Entities | `remem_list_entities` |
| Facts for an entity | `remem_get_entity_facts` |

## Write

Writes are **grokbot only**. The connector injects `grokbot` if you omit `namespace` and will not write `default`.

| Need | Tool |
| --- | --- |
| Store text | `remem_ingest` (`POST /v1/documents/ingest`, JSON `content` required, `Idempotency-Key`) |
| Extract facts from an ingested doc | `remem_extract_facts` (namespace query param forced to `grokbot`) |

## Never

- Claude session-memory skill or `remem-dev-sessions` hooks
- `git+https://github.com/asimgilani/remem.git` until that repo is public
- `remem-io/remem` or `rememhq-mcp`
- Spawning `.venv/bin/python`
