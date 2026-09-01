# remem_query

`remem_query` is the Grok Bot Remem plugin tool that asks Remem for relevant context and returns the raw JSON body of `POST /v1/query` over stdio MCP.

## Sub-features

- `query-probe`: send a clearly labeled verification probe string as `query`.
- `query-grokbot-namespace`: pass `namespaces` `["grokbot"]` so the live read does not require `default` access and never injects `["*"]`.
- `query-raw-json`: observe raw Remem JSON, not `remem_search` formatted chunks.

## How to get to it (user POV)

A Grok Bot user needs recall from Remem and invokes the `remem_query` MCP tool. There is no page, window, or mobile screen. The child is `python3 ${PLUGIN_ROOT}/server.py`. The user-visible result is the tool's JSON text.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- This drive is read-only. It reads `grokbot` only. It must not write `default` and must not inject `["*"]`.

- **Ask Remem.** From the repo root, run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_query`. The helper opens a fresh stdio session, `session.initialize()`, then `session.call_tool("remem_query", {"query": "verify-remem-grokbot remem_query verification probe", "namespaces": ["grokbot"]})`.
- **Observe the tool JSON.** `/tmp/verify-remem-grokbot-evidence/drive-remem_query.json` (and `.txt`) exist. Result text is Remem query JSON, does not start with `HTTP ` or `Error:`, and is redacted. Empty `results` is still a live pass.
- **Confirm the path.** The action was `session.call_tool`. The helper did not call `dispatch_tool`.

## Gotchas

- This is `POST /v1/query`, not `GET /v1/search`, and not the formatted text from `remem_search`.
- `scripts/prove_live.py` may exercise a similar query shape via `dispatch_tool`. That script is not this recipe.
- If the key is unset, the helper FAIL LOUDs and exits 2. Do not invent a 2xx.
- Omitting `namespaces` makes the connector read `["default", "grokbot"]`. This key has no read access to `default` (HTTP 403). The live recipe must pass `["grokbot"]`.
- If the body shows null `extracted` and/or `classifier_model` unavailable, FAIL LOUD. Do not claim ASI-9 Done.
