# remem_get_entity_facts

`remem_get_entity_facts` is the Grok Bot Remem plugin tool that fetches facts for one entity UUID from `GET /v1/entities/{entity_id}/facts`.

## Sub-features

- `entity-facts-uuid`: `entity_id` must be a canonical UUID.
- `entity-facts-filters`: optional `latest_only` and `fact_type`.
- `entity-facts-empty`: `No facts found.` under the entity heading is an allowed body.

## How to get to it (user POV)

A Grok Bot user has an entity id (usually from `remem_list_entities`) and invokes `remem_get_entity_facts`. There is no entity profile page. The result is formatted facts for that id.

## Driving it with verify-remem-grokbot

Preconditions:

- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch` printed `ready`.
- `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor` exited 0 with `process_up` true, ten tools, health 200, and `remem_api_key_present` true.
- `REMEM_API_KEY` is already in the process environment. Do not paste or print a key.
- A canonical entity UUID exists. This run may not have one.

- **Optional live drive.** This verification run may not drive `remem_get_entity_facts` live. If driven, from the repo root run `python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_get_entity_facts`. The helper may call `remem_list_entities` first, parse an entity UUID, then `session.call_tool("remem_get_entity_facts", {"entity_id": "<canonical UUID>"})`.
- **Observe entity facts when driven.** `/tmp/verify-remem-grokbot-evidence/drive-remem_get_entity_facts.json` would hold the action and result. Text must not start with `HTTP ` or `Error:`. If no entity UUID is available, the helper must fail honest and must not invent a 2xx. Do not report this tool verified if that file was not produced by a passing drive.

## Gotchas

- This file is a stub. Skipping it is honest. Do not mark it verified because `remem_list_entities` printed a name.
- Non-UUID ids fail in the connector (`entity_id must be a canonical UUID`). Do not invent an entity id.
- GET namespace params are comma-separated.
- If the key is unset, FAIL LOUD and exit 2.
