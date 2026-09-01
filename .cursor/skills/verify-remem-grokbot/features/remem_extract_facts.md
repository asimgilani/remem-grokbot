# remem_extract_facts

`remem_extract_facts` is the Grok Bot Remem plugin tool that triggers fact extraction on a document via `POST /v1/documents/{document_id}/extract-facts`.

## Sub-features

- `extract-uuid`: `document_id` must be a canonical UUID.
- `extract-grokbot`: the write namespace is `grokbot` (never `default`).
- `extract-leftover`: null `extracted` and/or `classifier_model` unavailable is asimgilani/remem#36 and must FAIL LOUD.

## How to get to it (user POV)

A Grok Bot user has a document id and wants Remem to extract facts, then invokes `remem_extract_facts`. There is no extract button in a UI. The result is JSON from the extract-facts call.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- A canonical document UUID exists (typically from `remem_ingest` with `return_id` true). This run may not have one.

- **Optional live drive.** This verification run may not drive `remem_extract_facts` live. If driven, from the repo root run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_extract_facts`. The helper may ingest a `grokbot` probe, then `session.call_tool("remem_extract_facts", {"document_id": "<canonical UUID>", "namespace": "grokbot"})`.
- **Observe extract JSON when driven.** `/tmp/verify-remem-grokbot-evidence/drive-remem_extract_facts.json` would hold the action and result. Text must not start with `HTTP ` or `Error:`. If `extracted` is null and/or `classifier_model` is unavailable, the helper FAIL LOUDs and exits non-zero. Do not report this tool verified if that file was not produced by a passing drive.

## Gotchas

- This file is a stub. Skipping it is honest. Do not mark it verified because ingest returned a `job_id`.
- Classifier leftover (asimgilani/remem#36): null `extracted` and/or `classifier_model` unavailable is an upstream Remem issue. The harness MUST fail loud if it observes that leftover. Do not claim ASI-9 Done. Do not loop `remem_extract_facts` as a completion gate.
- Writes stay `grokbot`. Never write `default`.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
