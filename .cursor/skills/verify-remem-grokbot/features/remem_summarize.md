# remem_summarize

`remem_summarize` is the Grok Bot Remem plugin tool that asks Remem for a rich synthesized answer with sources via `POST /v1/query` `mode=rich` `synthesize=true`.

## Sub-features

- `summarize-question`: the required argument is `question`, not `query`.
- `summarize-rich`: the connector sends `mode=rich` and `synthesize=true`.
- `summarize-empty`: `No synthesis returned.` is an allowed live body when Remem has nothing to synthesize.

## How to get to it (user POV)

A Grok Bot user asks a natural-language question and invokes `remem_summarize` with that question. There is no summarize button in a UI. The result is synthesis text plus a `**Sources:**` block, or `No synthesis returned.`

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- The helper must pass `question`. A drive that sends `query` instead is invalid.

- **Ask a question.** From the repo root, run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_summarize`. The helper opens a fresh stdio session and `session.call_tool("remem_summarize", {"question": "verify-remem-grokbot remem_summarize verification probe"})`.
- **Observe synthesis or the empty line.** `/tmp/verify-remem-grokbot-evidence/drive-remem_summarize.json` (and `.txt`) exist. Result text is synthesis plus sources, or `No synthesis returned.`, and does not start with `HTTP ` or `Error:`.
- **Confirm the argument.** Evidence `arguments` include `question` and do not use `query` as the summarize field.

## Gotchas

- The tool schema requires `question`. Passing `query` is the wrong tool shape (that is `remem_query`).
- Rich synthesize can be slower than fast query. Wait for the helper to exit; do not kill the stdio child mid-call.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
