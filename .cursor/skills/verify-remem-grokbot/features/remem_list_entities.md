# remem_list_entities

`remem_list_entities` is the Grok Bot Remem plugin tool that lists memory entities from `GET /v1/entities`.

## Sub-features

- `list-entities`: optional `entity_type`, `limit`, and `offset`.
- `list-empty`: `No entities found.` is an allowed live body.
- `list-namespaces`: omitted reads become comma-separated `default,grokbot` on the GET.

## How to get to it (user POV)

A Grok Bot user wants to see which entities Remem knows and invokes `remem_list_entities`. There is no entity sidebar. The result is a formatted list with names, types, counts, and ids, or `No entities found.`

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- This account may have zero entities. That is not a reason to invent rows.

- **Optional live drive.** This verification run may not drive `remem_list_entities` live. If driven, from the repo root run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_list_entities`. The helper opens a fresh stdio session and `session.call_tool("remem_list_entities", {"limit": 5})`.
- **Observe the list when driven.** `/tmp/verify-remem-grokbot-evidence/drive-remem_list_entities.json` would hold the action and result. Text is a formatted `**Entities**` list or `No entities found.`, and must not start with `HTTP ` or `Error:`. Do not report this tool verified if that file was not produced by a passing drive.

## Gotchas

- This file is a stub. Skipping it is honest. Do not mark it verified because query JSON mentioned an entity name.
- Entity ids in the list are the input to `remem_get_entity_facts`. They must be canonical UUIDs.
- If the key is unset, FAIL LOUD and exit 2. Do not invent a 2xx.
