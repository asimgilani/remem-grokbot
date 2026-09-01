# remem-grokbot feature map

Behavior-level inventory of the Grok Bot Remem plugin (`remem-grokbot`) stdio MCP surface. Agents use this map to decide which `remem_*` tool to drive and what evidence counts. Humans use it as the regression checklist. This is not a GUI app. The inventory is these ten tools only.

## Baseline preconditions

- Repo root contains `server.py` and `mcp.json`. Spawn is `python3 ${PLUGIN_ROOT}/server.py` (system `python3`, never `.venv/bin/python`).
- Pins `mcp==1.26.0` and `httpx==0.28.1` are importable after `launch`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready` (MCP `initialize` succeeded on a short-lived stdio child).
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0: process up, exactly the ten tool names below, `GET https://api.remem.io/health` is HTTP 200, `remem_api_key_present` is true.
- `REMEM_API_KEY` is already in the process environment. Do not paste a key. Do not print, log, or commit a key. Do not ask anyone to paste a key.
- There is no long-lived HTTP server to own. Each helper command opens its own stdio session and closes it.
- This harness writes `grokbot` only for ingest/product-policy recipes. Never write `default`. Do not set `REMEM_DEFAULT_NAMESPACE` for a verification run.
- Rec B `remem_query` is a read-only live drive that passes `namespaces: ["testing"]`. Grok Bot house writes `grokbot`; this Cloud Agents test key reads/writes `testing`. Do not fall back to grokbot or default. Do not POST `/v1/namespaces`.
- Omitted reads become `["default", "grokbot"]`. Never inject `["*"]`.
- Document and entity ids are canonical UUIDs.

## Driving conventions

- Start every recipe from the baseline unless that feature file says otherwise.
- Drive with `session.call_tool` through the helper. Treat every command as literal.
- Never import or call `remem_grokbot.server.dispatch_tool` as the drive path.
- Never start Playwright, CDP, Electron, or a browser. This surface is stdio MCP.
- `remem_ingest` always includes `namespace` `grokbot` and `return_id` true.
- `remem_summarize` always passes `question` (not `query`).
- `remem_query` Rec B live recipe passes `namespaces: ["testing"]` and a clearly labeled verification probe string. `remem_search` uses a clearly labeled verification probe string.
- GET namespace params on the wire are comma-separated (`default,grokbot` when omitted). POST bodies use a JSON array.
- Do not treat `scripts/prove_live.py` as a feature recipe. It is a payload/redaction lever only.
- Restore nothing in Remem (probe documents titled with `verify-remem-grokbot` are safe to leave). Do not delete proof artifacts during cleanup.

## Proof and skip reporting

- The relevant feature file defines the coverage set for a fix.
- Exercise the real `remem_*` path over stdio. Record the action (`call_tool` name + arguments) and the resulting tool JSON or formatted text.
- Writes: prove `grokbot` in the arguments and in any returned write namespace. A live ingest proof includes parseable JSON with `job_id`.
- Reads: a body that does not start with `HTTP ` or `Error:` is the live shape. Empty Remem `results` / `No results found.` / `No facts found.` / `No synthesis returned.` can still be a live pass.
- Redact evidence: keys containing `key` (except `idempotency`) become `"<redacted>"`; strings starting with `vlt_` become `"vlt_<redacted>"`. Never write `REMEM_API_KEY` material.
- If `extracted` is null and/or `classifier_model` is unavailable, FAIL LOUD. That leftover is asimgilani/remem#36. Do not claim ASI-9 Done. Do not loop `remem_extract_facts` as a completion gate.
- When a path is not driven this run, name the tool file, say it is a stub or unmet precondition, and do not report it as verified through a different tool.
- Mocks and `tests/` shape tests do not count as a live Remem pass.

## Entry contract

Every feature file uses the same four H2s:

1. `Sub-features`
2. `How to get to it (user POV)`
3. `Driving it with verify-remem-grokbot`
4. `Gotchas`

Each file starts with an H1 and one paragraph describing the tool. `Driving it with verify-remem-grokbot` starts with `Preconditions:` then labeled bullets that pair each user action with the exact helper command and the observable result.

## Tools

Live recipes (full preconditions and helper bullets):

- [remem_query](remem_query.md): raw JSON from `POST /v1/query`. Rec B live recipe reads `testing` only.
- [remem_search](remem_search.md): formatted fast search (`POST /v1/query` `mode=fast`, not `GET /v1/search`).
- [remem_summarize](remem_summarize.md): rich synthesis; argument is `question`.
- [remem_get_document](remem_get_document.md): fetch one document by canonical UUID.
- [remem_ingest](remem_ingest.md): JSON ingest to `POST /v1/documents/ingest` (not `POST /v1/ingest`).

Stubs (same four H2s; this run may not drive them live):

- [remem_get_document_chunks](remem_get_document_chunks.md): decrypted chunks for a document UUID.
- [remem_memory_query](remem_memory_query.md): query with `include_facts=true`.
- [remem_list_entities](remem_list_entities.md): list memory entities.
- [remem_get_entity_facts](remem_get_entity_facts.md): facts for an entity UUID.
- [remem_extract_facts](remem_extract_facts.md): trigger fact extraction; leftover #36 fails loud.
