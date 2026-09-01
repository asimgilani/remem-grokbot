# remem_ingest

`remem_ingest` is the Grok Bot Remem plugin tool that writes text into Remem with JSON `content` on `POST /v1/documents/ingest`.

## Sub-features

- `ingest-json-content`: body is JSON `content` on `POST /v1/documents/ingest`, not `POST /v1/ingest`.
- `ingest-grokbot`: writes `namespace` `grokbot` (never `default`).
- `ingest-return-id`: `return_id` true so the tool JSON can include a document UUID plus `job_id`.

## How to get to it (user POV)

A Grok Bot user wants Remem to remember a note and invokes `remem_ingest` with text. There is no upload dialog. The user-visible result is JSON (`job_id`, and a document id when `return_id` is true).

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- This drive writes. The write namespace must be `grokbot`. Never write `default`.

- **Ingest probe text.** From the repo root, run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_ingest`. The helper opens a fresh stdio session and `session.call_tool("remem_ingest", {"title": "verify-remem-grokbot remem_ingest probe", "content": "verify-remem-grokbot remem_ingest verification probe. Safe to ignore.", "namespace": "grokbot", "return_id": true, "source": "api"})`.
- **Observe ingest JSON.** `/tmp/verify-remem-grokbot-evidence/drive-remem_ingest.json` (and `.txt`) exist. Result text is parseable JSON with `job_id`, does not start with `HTTP ` or `Error:`, and is redacted. `return_id` true may also yield a document UUID.
- **Confirm grokbot.** Evidence arguments include `namespace` `grokbot` and `return_id` true. A write to `default` fails this recipe.

## Gotchas

- Live path is `POST /v1/documents/ingest`. `POST /v1/ingest` is forbidden.
- OpenAPI may list multipart; this plugin sends JSON `content` first. Do not invent a third path.
- A `job_id` is queued ingest, not a guarantee the worker indexed the text for later search.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
