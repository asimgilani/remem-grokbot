# remem_get_document

`remem_get_document` is the Grok Bot Remem plugin tool that fetches one document by canonical UUID from `GET /v1/documents/{document_id}`.

## Sub-features

- `get-document-uuid`: `document_id` must be a canonical UUID or the connector rejects it.
- `get-document-from-ingest`: this live recipe first writes a `grokbot` probe with `return_id` true, then fetches that UUID.
- `get-document-namespaces`: omitted reads become comma-separated `default,grokbot` on the GET.

## How to get to it (user POV)

A Grok Bot user already has a document id (from ingest or a prior query) and invokes `remem_get_document`. There is no document viewer window. The result is JSON for that document.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- The helper may ingest a probe into `grokbot` (never `default`) to obtain a UUID. That write is part of this recipe.

- **Fetch by UUID.** From the repo root, run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_get_document`. The helper opens one stdio session, `session.call_tool("remem_ingest", …)` with `namespace` `grokbot` and `return_id` true, then `session.call_tool("remem_get_document", {"document_id": "<canonical UUID>"})`.
- **Observe document JSON.** `/tmp/verify-remem-grokbot-evidence/drive-remem_get_document.json` (and `.txt`) exist. The get-document result is JSON, does not start with `HTTP ` or `Error:`, and the id used is a canonical UUID.
- **Confirm the write namespace.** The ingest step in the same evidence file used `grokbot` only.

## Gotchas

- Non-UUID ids fail in the connector (`document_id must be a canonical UUID`). Do not invent a document id.
- If ingest returns `job_id` without `document_id` / `id`, this drive cannot fetch. Fail honest. Do not invent a 2xx get.
- GET namespace params are comma-separated. Do not expect a JSON array on the query string.
- If the key is unset, FAIL LOUD and exit 2.
