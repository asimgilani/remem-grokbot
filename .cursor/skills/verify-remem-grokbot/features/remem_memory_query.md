# remem_memory_query

`remem_memory_query` is the Grok Bot Remem plugin tool that queries Remem's knowledge graph via `POST /v1/query` with `include_facts=true` and returns formatted fact lines.

## Sub-features

- `memory-probe`: send a query string and receive formatted facts or `No facts found.`
- `memory-entity`: optional `entity` name scopes facts.
- `memory-latest`: `latest_only` maps to `facts_only_latest` on the query body.

## How to get to it (user POV)

A Grok Bot user wants stored facts (not only document chunks) and invokes `remem_memory_query`. There is no graph UI. The result is a list of fact lines or `No facts found.`

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- Facts may be absent in this account. `No facts found.` is an allowed body, not a reason to invent facts.

- **Optional live drive.** This verification run may not drive `remem_memory_query` live. If driven, from the repo root run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_memory_query`. The helper opens a fresh stdio session and `session.call_tool("remem_memory_query", {"query": "verify-remem-grokbot remem_memory_query verification probe"})`.
- **Observe fact lines when driven.** `/tmp/verify-remem-grokbot-evidence/drive-remem_memory_query.json` would hold the action and result. Text is formatted facts or `No facts found.`, and must not start with `HTTP ` or `Error:`. Do not report this tool verified if that file was not produced by a passing drive.

## Gotchas

- This file is a stub. Skipping it is honest. Do not mark it verified because `remem_query` returned document JSON.
- This is still `POST /v1/query`, with `include_facts=true`. It is not a separate memory host.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
