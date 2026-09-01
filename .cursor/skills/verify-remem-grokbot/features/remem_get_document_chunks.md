# remem_get_document_chunks

`remem_get_document_chunks` is the Grok Bot Remem plugin tool that fetches decrypted chunks for a document UUID from `GET /v1/documents/{document_id}/chunks`.

## Sub-features

- `chunks-uuid`: `document_id` must be a canonical UUID.
- `chunks-include-content`: optional `include_content` (default true) and `limit`.
- `chunks-namespaces`: omitted reads become comma-separated `default,grokbot` on the GET.

## How to get to it (user POV)

A Grok Bot user has a document id and wants the chunk text, then invokes `remem_get_document_chunks`. There is no chunk pane. The result is JSON for that document's chunks.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- A canonical document UUID exists (typically from `remem_ingest` with `return_id` true). This run may not have one.

- **Optional live drive.** This verification run may not drive `remem_get_document_chunks` live. If driven, from the repo root run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_get_document_chunks`. The helper may ingest a `grokbot` probe to obtain a UUID, then `session.call_tool("remem_get_document_chunks", {"document_id": "<canonical UUID>"})`.
- **Observe chunk JSON when driven.** `/tmp/verify-remem-grokbot-evidence/drive-remem_get_document_chunks.json` would hold the action and result. Text must not start with `HTTP ` or `Error:`. Do not report this tool verified if that file was not produced by a passing drive.

## Gotchas

- This file is a stub. Skipping it is honest. Do not mark it verified because `remem_get_document` passed.
- Non-UUID ids fail in the connector. Do not invent a document id.
- Ingest `job_id` alone is not a chunk list. Chunks need a document UUID and a processed document.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
