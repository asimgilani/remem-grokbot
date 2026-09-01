---
name: verify-remem-grokbot
description: Drive the Grok Bot Remem plugin (remem-grokbot) over its stdio MCP surface (ten remem_* tools). Use when launching, doctoring, or proving remem_* behavior against https://api.remem.io with session.call_tool evidence.
---

# Verify remem-grokbot

This skill is the scripted way to launch, doctor, drive, and capture evidence for the Grok Bot Remem plugin (`asimgilani/remem-grokbot`). The user-facing surface is **stdio MCP**, not a web page, desktop window, or mobile app. A Grok Bot (or this harness) talks to a short-lived child: `python3 ${PLUGIN_ROOT}/server.py`, where `PLUGIN_ROOT` is the repo root that contains `server.py`. That child exposes exactly ten tools against `https://api.remem.io`. There is no long-lived HTTP server. Each helper command opens its own stdio session and closes it.

Read [features/README.md](features/README.md) before driving. `scripts/prove_live.py` is a lever for `remem_query` / `remem_ingest` payload and redaction shapes only. It is not this skill and not the Feature Map. Never import or call `remem_grokbot.server.dispatch_tool` as the drive path.

## Launch

The plugin spawn (from `README.md` / `mcp.json`) is:

```text
python3 ${PLUGIN_ROOT}/server.py
```

Use **system `python3`**. Pins are `mcp==1.26.0` and `httpx==0.28.1`. Alternative: `uv run --project . python server.py`. Never `.venv/bin/python`.

For verification, do not keep a daemon. Run the helper from the repo root:

```
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch
```

`launch` installs the pins with `python3 -m pip install 'mcp==1.26.0' 'httpx==0.28.1'` when `mcp` or `httpx` is missing, then opens one stdio child, waits until **MCP `initialize` succeeds**, prints `ready`, and closes the child. That initialize success is the ready signal. If initialize fails, do not drive.

Teardown is implicit: the stdio context closes the child. After a run (including a failed one), call `cleanup` so leftover helper-started PIDs do not linger.

## Doctor

One read-only check. Run it first whenever anything looks off:

```
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor
```

All four must pass or the instance is not worth driving:

1. **process up** — a stdio child accepts MCP `initialize`.
2. **tools** — `list_tools` is exactly these ten names, in this order: `remem_query`, `remem_search`, `remem_summarize`, `remem_get_document`, `remem_get_document_chunks`, `remem_memory_query`, `remem_list_entities`, `remem_get_entity_facts`, `remem_extract_facts`, `remem_ingest`.
3. **health** — `GET https://api.remem.io/health` is HTTP 200. This check is public. Do not send `REMEM_API_KEY` on it. Do not print the key.
4. **key present-but-unprinted** — `REMEM_API_KEY` is set in the **process environment** (boolean only). If unset: FAIL LOUD, say the key is unset in the process environment, say the mechanism checked is the process environment, print that no key was printed and no one was asked to paste, print that live drive was not proven, and exit 2. Do not invent a 2xx. Do not ask anyone to paste a key. Do not copy a key from anywhere.

Doctor prints redacted JSON with `process_up`, `tools_count`, `tool_names`, `health_http_status`, and `remem_api_key_present` (boolean). Exit 0 only if all four pass. Evidence copy: `/tmp/verify-remem-grokbot-evidence/doctor.json`.

## Drive

Drive the way a Grok Bot user does: MCP `session.call_tool` on a fresh stdio child. The spawn matches `tests/test_stdio.py`: `python3` + `PLUGIN_ROOT/server.py`, `PYTHONPATH` includes `PLUGIN_ROOT`, `cwd` is `PLUGIN_ROOT`. Never `dispatch_tool`. Never Playwright, CDP, Electron, or a browser.

```
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_query
```

Replace `remem_query` with any of the ten tool names. The helper opens a **new** stdio session, `initialize`, then `call_tool` with the recipe in the matching [features/](features/) file. This harness writes namespace `grokbot` only for ingest/product-policy writes (Grok Bot installs). Rec B cloud live `remem_query` recipe passes `namespaces: ["testing"]`. Grok Bot house writes `grokbot`; this Cloud Agents test key reads/writes `testing`. Never write `default`. Do not set `REMEM_DEFAULT_NAMESPACE` for a verification run. Omitted reads become `["default", "grokbot"]` and this test key cannot use those — do not fall back to grokbot or default. Never inject `["*"]`. Document and entity ids must be canonical UUIDs. `remem_ingest` sends `namespace` `grokbot` and `return_id` true. `remem_summarize` passes `question`. `remem_query` Rec B and `remem_search` use a clearly labeled verification probe string.

If `REMEM_API_KEY` is unset: FAIL LOUD (same rules as Doctor) and do not invent a 2xx. If tool text starts with `HTTP ` or `Error:`: FAIL LOUD with the HTTP line (first line / body prefix). Do not invent a 2xx. Do not loop. Do not POST `/v1/namespaces`. Do not fall back to grokbot or default. If the result shows the classifier leftover (`extracted` is null and/or `classifier_model` unavailable): FAIL LOUD, do not claim ASI-9 Done, do not loop `remem_extract_facts` as a completion gate.

Use the Feature Map. A proof that drives one convenient tool is incomplete when the change touches others listed there. Live recipes in this tree: `remem_query`, `remem_ingest`, `remem_get_document`, `remem_search`, `remem_summarize`. The other five files are stubs this run may not drive live.

## Evidence

Named directory (survives cleanup): `/tmp/verify-remem-grokbot-evidence`

- `doctor.json` — redacted doctor payload.
- `drive-<feature>.json` — the drive action (tool name + arguments) and the resulting tool JSON/text.
- `drive-<feature>.txt` — stdout transcript of that drive.

Proof standards:

- Exercise the real user path: `session.call_tool` over stdio for a real `remem_*` tool. Internal `dispatch_tool` does not count.
- Capture the **action** and the **resulting tool JSON/text**, not only an exit code.
- Writes land in `grokbot` only (ingest/product-policy). Confirm namespace in the ingest/extract arguments and in any returned write fields. Rec B `remem_query` is a read of `testing` only.
- Side effects: a successful `remem_ingest` returns parseable JSON with a `job_id` (and a document UUID when `return_id` is true). A successful query/search/summarize returns a body that does not start with `HTTP ` or `Error:`. Empty Remem results can still be a live pass.
- Redact before writing anything: keys whose names contain `key` (except `idempotency`) become `"<redacted>"`; strings starting with `vlt_` become `"vlt_<redacted>"`. Never write `REMEM_API_KEY` material. Doctor's key field is a boolean only.
- Mocks do not count for live Remem. Shape tests under `tests/` are not a live pass.

## Cleanup

```
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py cleanup
```

Kills **only** PIDs this helper started that are still alive (tracked under `/tmp/verify-remem-grokbot-run/`). Never kill by process name. Never delete `/tmp/verify-remem-grokbot-evidence`. After cleanup, that evidence directory must still exist if a doctor or drive wrote to it.

## Helpers

The helper is executable. Invoke it from the repo root exactly like this:

```
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py launch
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py doctor
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py drive remem_query
python3 .cursor/skills/verify-remem-grokbot/verify_remem_grokbot.py cleanup
```

`launch` / `doctor` / `drive` / `cleanup` are the only subcommands. `drive` takes one FEATURE: a tool name from the Feature Map. The helper resolves `PLUGIN_ROOT` as the repo root (two levels above `.cursor/skills/verify-remem-grokbot`, or by walking up until `server.py` exists).

Use `/maintain-verification-skill` to keep this map honest as the plugin changes.
