#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Never
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    httpx = None  # type: ignore[assignment]
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment]

TOOL_NAMES: tuple[str, ...] = (
    "remem_query",
    "remem_search",
    "remem_summarize",
    "remem_get_document",
    "remem_get_document_chunks",
    "remem_memory_query",
    "remem_list_entities",
    "remem_get_entity_facts",
    "remem_extract_facts",
    "remem_ingest",
)

HEALTH_URL = "https://api.remem.io/health"
EVIDENCE_DIR = Path("/tmp/verify-remem-grokbot-evidence")
RUN_DIR = Path("/tmp/verify-remem-grokbot-run")
PID_FILE = RUN_DIR / "pids.json"
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

SIMPLE_RECIPES: dict[str, dict[str, Any]] = {
    "remem_query": {
        "query": "verify-remem-grokbot remem_query verification probe",
        "namespaces": ["grokbot"],
    },
    "remem_search": {
        "query": "verify-remem-grokbot remem_search verification probe",
    },
    "remem_summarize": {
        "question": "verify-remem-grokbot remem_summarize verification probe",
    },
    "remem_memory_query": {
        "query": "verify-remem-grokbot remem_memory_query verification probe",
    },
    "remem_list_entities": {
        "limit": 5,
    },
}


def resolve_plugin_root() -> Path:
    here = Path(__file__).resolve().parent
    two_up = here.parents[2] if len(here.parents) >= 3 else here
    if (two_up / "server.py").is_file():
        return two_up
    for parent in (here, *here.parents):
        if (parent / "server.py").is_file():
            return parent
    print("FAIL: could not resolve PLUGIN_ROOT (no server.py).")
    raise SystemExit(1)


def _key_present() -> bool:
    return bool(os.environ.get("REMEM_API_KEY"))


def _fail_key_unset() -> None:
    print("FAIL LOUD: REMEM_API_KEY is unset in the process environment.")
    print("Mechanism checked: process environment.")
    print("No key was printed. No one was asked to paste a key.")
    print("Live drive was not proven. Do not invent a 2xx.")


def _redact(value: object) -> object:
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "key" in lowered and "idempotency" not in lowered:
                # Boolean presence flags must stay booleans. Never print the key.
                if isinstance(item, bool):
                    out[key] = item
                else:
                    out[key] = "<redacted>"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        secret = os.environ.get("REMEM_API_KEY") or ""
        if secret and secret in value:
            value = value.replace(secret, "<redacted>")
        if value.startswith("vlt_"):
            return "vlt_<redacted>"
        return value
    return value


def _has_classifier_leftover(value: object) -> bool:
    if isinstance(value, dict):
        if "extracted" in value and value["extracted"] is None:
            return True
        if "classifier_model" in value:
            model = value["classifier_model"]
            if model is None:
                return True
            if isinstance(model, str) and "unavailable" in model.lower():
                return True
        return any(_has_classifier_leftover(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_classifier_leftover(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        if "classifier_model" in lowered and "unavailable" in lowered:
            return True
        compact = re.sub(r"\s+", "", value)
        if '"extracted":null' in compact:
            return True
    return False


def _looks_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _first_uuid(text: str) -> str | None:
    match = UUID_RE.search(text)
    if match is None:
        return None
    raw = match.group(0)
    return raw if _looks_uuid(raw) else None


def _document_id_from_ingest(text: str) -> str | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    for field in ("document_id", "id"):
        raw = data.get(field)
        if isinstance(raw, str) and _looks_uuid(raw):
            return raw
    return None


def _ingest_arguments(label: str) -> dict[str, Any]:
    return {
        "title": f"verify-remem-grokbot {label} probe",
        "content": f"verify-remem-grokbot {label} verification probe. Safe to ignore.",
        "namespace": "grokbot",
        "return_id": True,
        "source": "api",
    }


def _child_pids() -> set[int]:
    mine = os.getpid()
    found: set[int] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ppid = None
        for line in status.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
                break
        if ppid == mine:
            found.add(int(entry.name))
    return found


def _load_pids() -> list[int]:
    if not PID_FILE.is_file():
        return []
    try:
        data = json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    pids: list[int] = []
    for item in data:
        try:
            pids.append(int(item))
        except (TypeError, ValueError):
            continue
    return pids


def _save_pids(pids: list[int]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    unique = sorted({int(pid) for pid in pids})
    PID_FILE.write_text(json.dumps(unique) + "\n", encoding="utf-8")


def _record_pids(pids: set[int]) -> None:
    current = _load_pids()
    current.extend(pids)
    _save_pids(current)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _deps_missing() -> bool:
    return importlib.util.find_spec("mcp") is None or importlib.util.find_spec("httpx") is None


def _ensure_deps() -> None:
    if not _deps_missing():
        return
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "mcp==1.26.0",
            "httpx==0.28.1",
        ]
    )
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _mcp_ready() -> bool:
    return ClientSession is not None and StdioServerParameters is not None and stdio_client is not None


def _write_json(path: Path, payload: object) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    redacted = _redact(payload)
    path.write_text(json.dumps(redacted, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    redacted = _redact(text)
    if not isinstance(redacted, str):
        redacted = json.dumps(redacted, indent=2)
    path.write_text(redacted + "\n", encoding="utf-8")


def _result_text(result: object) -> str:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, list):
        content = result
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    if parts:
        return "\n".join(parts)
    return str(result)


def _public_health_status() -> int:
    request = Request(HEALTH_URL, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError:
        return 0


@asynccontextmanager
async def _stdio_session() -> AsyncIterator[Any]:
    if not _mcp_ready():
        raise RuntimeError("mcp is not importable. Run launch first.")
    root = resolve_plugin_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(
        command="python3",
        args=[str(root / "server.py")],
        env=env,
        cwd=str(root),
    )
    before = _child_pids()
    async with stdio_client(params) as (read, write):
        after = _child_pids()
        _record_pids(after - before)
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(
    session: Any,
    calls: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> tuple[str, int | None]:
    result = await session.call_tool(name, arguments)
    text = _result_text(result)
    calls.append({"tool": name, "arguments": arguments, "result_text": text})
    if text.startswith("HTTP ") or text.startswith("Error:"):
        print(f"FAIL: {name} text starts with HTTP or Error:. Live 2xx was not proven.")
        return text, 2
    parsed: object | None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if _has_classifier_leftover(text) or (parsed is not None and _has_classifier_leftover(parsed)):
        print(
            "FAIL LOUD: observed classifier leftover "
            "(null extracted and/or classifier_model unavailable)."
        )
        print("Upstream Remem issue (asimgilani/remem#36). Do not claim ASI-9 Done.")
        print("Do not loop remem_extract_facts as a completion gate.")
        return text, 2
    if bool(getattr(result, "isError", False)):
        print(f"FAIL: {name} returned isError.")
        return text, 2
    return text, None


async def _drive_one(
    session: Any,
    calls: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> tuple[bool, int]:
    _text, err = await _call_tool(session, calls, name, arguments)
    if err is not None:
        return False, err
    return True, 0


async def _drive_ingest(session: Any, calls: list[dict[str, Any]]) -> tuple[bool, int]:
    text, err = await _call_tool(session, calls, "remem_ingest", _ingest_arguments("remem_ingest"))
    if err is not None:
        return False, err
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print("FAIL: remem_ingest did not return JSON.")
        return False, 2
    if not isinstance(data, dict) or "job_id" not in data:
        print("FAIL: remem_ingest missing job_id.")
        return False, 2
    return True, 0


async def _drive_after_ingest(
    session: Any,
    calls: list[dict[str, Any]],
    name: str,
    extra: dict[str, Any],
) -> tuple[bool, int]:
    ingest_text, err = await _call_tool(session, calls, "remem_ingest", _ingest_arguments(name))
    if err is not None:
        return False, err
    document_id = _document_id_from_ingest(ingest_text)
    if document_id is None:
        print(f"FAIL: {name} needs a canonical document UUID from remem_ingest return_id.")
        return False, 2
    arguments = {"document_id": document_id, **extra}
    return await _drive_one(session, calls, name, arguments)


async def _drive_query(session: Any, calls: list[dict[str, Any]]) -> tuple[bool, int]:
    _ingest_text, err = await _call_tool(
        session, calls, "remem_ingest", _ingest_arguments("remem_query")
    )
    if err is not None:
        return False, err
    return await _drive_one(session, calls, "remem_query", SIMPLE_RECIPES["remem_query"])


async def _drive_entity_facts(session: Any, calls: list[dict[str, Any]]) -> tuple[bool, int]:
    listed, err = await _call_tool(session, calls, "remem_list_entities", {"limit": 5})
    if err is not None:
        return False, err
    entity_id = _first_uuid(listed)
    if entity_id is None:
        print("FAIL: remem_get_entity_facts needs a canonical entity UUID. None was listed.")
        return False, 2
    return await _drive_one(session, calls, "remem_get_entity_facts", {"entity_id": entity_id})


async def _drive_feature(session: Any, feature: str, calls: list[dict[str, Any]]) -> tuple[bool, int]:
    if feature == "remem_query":
        return await _drive_query(session, calls)
    if feature in SIMPLE_RECIPES:
        return await _drive_one(session, calls, feature, SIMPLE_RECIPES[feature])
    if feature == "remem_ingest":
        return await _drive_ingest(session, calls)
    if feature == "remem_get_document":
        return await _drive_after_ingest(session, calls, "remem_get_document", {})
    if feature == "remem_get_document_chunks":
        return await _drive_after_ingest(session, calls, "remem_get_document_chunks", {})
    if feature == "remem_extract_facts":
        return await _drive_after_ingest(
            session,
            calls,
            "remem_extract_facts",
            {"namespace": "grokbot"},
        )
    if feature == "remem_get_entity_facts":
        return await _drive_entity_facts(session, calls)
    unreachable: Never = feature  # type: ignore[assignment]
    raise SystemExit(f"unhandled feature: {unreachable}")


async def _launch_once() -> int:
    async with _stdio_session():
        print("ready")
    return 0


async def _doctor_once() -> tuple[dict[str, Any], int]:
    process_up = False
    tool_names: list[str] = []
    try:
        async with _stdio_session() as session:
            process_up = True
            listed = await session.list_tools()
            tool_names = [tool.name for tool in listed.tools]
    except Exception as exc:
        print(f"FAIL: stdio initialize/list_tools: {exc}")
    health_status = _public_health_status()
    key_present = _key_present()
    payload = {
        "process_up": process_up,
        "tools_count": len(tool_names),
        "tool_names": tool_names,
        "health_http_status": health_status,
        "remem_api_key_present": key_present,
    }
    tools_ok = tool_names == list(TOOL_NAMES)
    health_ok = health_status == 200
    if not process_up:
        print("FAIL: process is not up (MCP initialize did not succeed).")
    if not tools_ok:
        print("FAIL: list_tools is not the ten remem_* names in TOOL_NAMES order.")
    if not health_ok:
        print(f"FAIL: GET {HEALTH_URL} HTTP {health_status} (want 200).")
    if not key_present:
        _fail_key_unset()
    print(json.dumps(_redact(payload), indent=2))
    _write_json(EVIDENCE_DIR / "doctor.json", payload)
    if not key_present:
        return payload, 2
    if process_up and tools_ok and health_ok and key_present:
        return payload, 0
    return payload, 1


def cmd_launch() -> int:
    _ensure_deps()
    if not _mcp_ready() or httpx is None:
        print("FAIL: mcp/httpx still missing after install.")
        return 1
    try:
        return asyncio.run(_launch_once())
    except Exception as exc:
        print(f"FAIL: launch initialize: {exc}")
        return 1


def cmd_doctor() -> int:
    if not _mcp_ready():
        print("FAIL: mcp is not importable. Run launch first.")
        return 1
    try:
        _payload, code = asyncio.run(_doctor_once())
    except Exception as exc:
        print(f"FAIL: doctor: {exc}")
        return 1
    return code


def cmd_drive(feature: str) -> int:
    if feature not in TOOL_NAMES:
        print(f"FAIL: unknown feature {feature}.")
        return 1
    if not _key_present():
        _fail_key_unset()
        _write_json(
            EVIDENCE_DIR / f"drive-{feature}.json",
            {
                "feature": feature,
                "ok": False,
                "calls": [],
                "error": "REMEM_API_KEY unset in the process environment",
            },
        )
        _write_text(
            EVIDENCE_DIR / f"drive-{feature}.txt",
            "FAIL LOUD: REMEM_API_KEY is unset in the process environment.",
        )
        return 2
    if not _mcp_ready():
        print("FAIL: mcp is not importable. Run launch first.")
        return 1
    calls: list[dict[str, Any]] = []
    ok = False
    code = 1
    error = None
    try:
        async def _run() -> tuple[bool, int]:
            async with _stdio_session() as session:
                return await _drive_feature(session, feature, calls)

        ok, code = asyncio.run(_run())
    except Exception as exc:
        error = str(exc)
        print(f"FAIL: drive {feature}: {exc}")
        ok = False
        code = 1
    payload = {
        "feature": feature,
        "ok": ok,
        "calls": calls,
    }
    if error:
        payload["error"] = error
    _write_json(EVIDENCE_DIR / f"drive-{feature}.json", payload)
    lines = [f"feature={feature}", f"ok={ok}"]
    for call in calls:
        lines.append(f"tool={call['tool']}")
        lines.append(json.dumps(_redact(call.get("arguments")), indent=2))
        result_text = call.get("result_text", "")
        redacted_result = _redact(result_text)
        lines.append(str(redacted_result))
    _write_text(EVIDENCE_DIR / f"drive-{feature}.txt", "\n".join(lines))
    if ok:
        print(f"drive {feature} ok")
        return 0
    print(f"drive {feature} failed")
    return code


def cmd_cleanup() -> int:
    pids = _load_pids()
    for pid in pids:
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    time.sleep(0.3)
    for pid in pids:
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            continue
    if PID_FILE.is_file():
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    if RUN_DIR.is_dir():
        try:
            next(RUN_DIR.iterdir())
        except StopIteration:
            try:
                RUN_DIR.rmdir()
            except OSError:
                pass
    print("cleanup done")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="verify_remem_grokbot.py",
        description="Launch, doctor, drive, and clean up remem-grokbot stdio MCP verification.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("launch", help="Install pins if needed and prove MCP initialize.")
    sub.add_parser("doctor", help="Read-only process, tools, health, and key-present check.")
    drive = sub.add_parser("drive", help="call_tool one remem_* feature over a fresh stdio session.")
    drive.add_argument("feature", choices=TOOL_NAMES)
    sub.add_parser("cleanup", help="Kill helper-started PIDs only. Keep evidence.")
    args = parser.parse_args()
    command = args.command
    if command == "launch":
        return cmd_launch()
    if command == "doctor":
        return cmd_doctor()
    if command == "drive":
        return cmd_drive(args.feature)
    if command == "cleanup":
        return cmd_cleanup()
    unreachable: Never = command  # type: ignore[assignment]
    raise SystemExit(f"unhandled command: {unreachable}")


if __name__ == "__main__":
    raise SystemExit(main())
