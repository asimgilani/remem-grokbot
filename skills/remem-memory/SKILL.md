---
name: remem-memory
description: Use Remem as Grok Bot memory. Read prefer default. Write grokbot only. Fail loud if Remem is down.
---

# Remem memory (Grok Bot)

Use the ten `remem_*` tools on this plugin. Do not invent a second memory store.

## Read

Prefer namespace `default` for house memory. Also search `grokbot` when the connector omitted `namespaces` (it sends `["default", "grokbot"]`). Do not silently switch to `["*"]`.

Use `remem_query` for raw recall. Use `remem_search` for formatted chunks. Use `remem_summarize` with argument `question`.

## Write

Write only to `grokbot`. Never write `default`. If a tool omits `namespace`, the connector still writes `grokbot`.

Use `remem_ingest` with JSON `content`. Path is `POST /v1/documents/ingest`. Not `POST /v1/ingest`.

## Fail loud

If Remem is down (`https://api.remem.io/health` or docs/OpenAPI unreachable), stop. Do not invent paths, fixtures, or a successful recall.

If `REMEM_API_KEY` is unset, stop. Do not ask anyone to paste a key. Do not print a key.

## Do not

- Install the macOS Claude plugin
- Install catalog `53852812`
- Use `asimgilani/remem-memory`
- Use `https://mcp.remem.io` as a working remote MCP
- Use `uvx git+https://github.com/asimgilani/remem.git` while that public repo 404s
- Spawn `.venv/bin/python`
- Treat HTTP `/home/box/lab/remem/query.py` as v1
