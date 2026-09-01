# remem_search

`remem_search` is the Grok Bot Remem plugin tool that runs a fast Remem search and returns formatted title/score/chunk text from `POST /v1/query` with `mode=fast`.

## Sub-features

- `search-probe`: send a clearly labeled verification probe string as `query`.
- `search-fast-post`: the wire call is `POST /v1/query` `mode=fast`, not `GET /v1/search`.
- `search-formatted`: observe formatted chunks or `No results found.`, not raw query JSON.

## How to get to it (user POV)

A Grok Bot user wants readable search hits and invokes `remem_search`. There is no search box in a browser. The result is formatted tool text over stdio MCP.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- This drive is read-only. Omitted reads stay `["default", "grokbot"]`.

- **Search Remem.** From the repo root, run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_search`. The helper opens a fresh stdio session and `session.call_tool("remem_search", {"query": "verify-remem-grokbot remem_search verification probe"})`.
- **Observe formatted hits.** `/tmp/verify-remem-grokbot-evidence/drive-remem_search.json` (and `.txt`) exist. Result text is formatted chunks (`**title** (score: …)`) or `No results found.`, and does not start with `HTTP ` or `Error:`.
- **Confirm the path.** The action was `session.call_tool("remem_search", …)`. Do not accept a `GET /v1/search` client as proof.

## Gotchas

- Agents sometimes reach for `GET /v1/search`. This plugin does not. Proof is `remem_search` over stdio.
- Do not require raw JSON. Formatted empty (`No results found.`) is a live pass.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
