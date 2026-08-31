from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from remem_grokbot.client import RememClient
from remem_grokbot.policy import NamespacePolicy
from remem_grokbot.server import dispatch_tool


def _redact(value: object) -> object:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if "key" in lowered and "idempotency" not in lowered:
                out[key] = "<redacted>"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and value.startswith("vlt_"):
        return "vlt_<redacted>"
    return value


async def _main() -> int:
    key_set = bool(os.environ.get("REMEM_API_KEY"))
    if not key_set:
        print("ASI-7 FAIL LOUD: REMEM_API_KEY is unset in the process environment.")
        print("Mechanism checked: process environment (Cloud Agent env / plugin secret field).")
        print("No key was printed. No one was asked to paste a key.")
        print("Live remem_query and remem_ingest were not run. Do not invent a 2xx.")
        return 2

    health = RememClient()
    try:
        health_body = await health.request("GET", "/health")
        ready_body = await health.request("GET", "/health/ready")
    except Exception as exc:
        print(f"ASI-7 FAIL LOUD: https://api.remem.io/health failed: {exc}")
        return 2

    print("health", json.dumps(_redact(health_body)))
    print("ready", json.dumps(_redact(ready_body)))

    policy = NamespacePolicy.from_env()
    client = RememClient()

    query_result = await dispatch_tool(
        "remem_query",
        {"query": "ASI-7 live prove query", "namespaces": ["default", "grokbot"]},
        client=client,
        policy=policy,
    )
    query_text = query_result[0].text
    print("remem_query_tool", query_text[:2000])
    if query_text.startswith("HTTP ") or query_text.startswith("Error:"):
        print("ASI-7 FAIL: remem_query did not return 2xx JSON.")
        return 2

    ingest_explicit = await dispatch_tool(
        "remem_ingest",
        {
            "title": "ASI-7 live prove ingest",
            "content": "ASI-7 remem-grokbot live prove. Safe to ignore.",
            "namespace": "grokbot",
            "return_id": True,
            "source": "api",
        },
        client=client,
        policy=policy,
    )
    explicit_text = ingest_explicit[0].text
    print("remem_ingest_explicit", explicit_text[:2000])
    try:
        explicit_json = json.loads(explicit_text)
    except json.JSONDecodeError:
        print("ASI-7 FAIL: remem_ingest (namespace grokbot) did not return JSON.")
        print("OpenAPI 0.1.0 lists ingest as multipart/form-data.")
        print("Live docs also document JSON content on POST /v1/documents/ingest.")
        print("JSON was tried first. No third path was invented.")
        return 2
    if "job_id" not in explicit_json:
        print("ASI-7 FAIL: remem_ingest missing job_id.")
        print("OpenAPI ingest content-type: multipart/form-data.")
        print("Live error body:", explicit_text[:2000])
        return 2

    ingest_omitted = await dispatch_tool(
        "remem_ingest",
        {
            "title": "ASI-7 omitted-namespace ingest",
            "content": "ASI-7 omitted namespace still grokbot.",
            "return_id": True,
            "source": "api",
        },
        client=client,
        policy=policy,
    )
    omitted_text = ingest_omitted[0].text
    print("remem_ingest_omitted", omitted_text[:2000])
    print("forced_write_namespace", policy.resolve_write(None))

    ready_status = ready_body.get("status") if isinstance(ready_body, dict) else None
    worker = None
    if isinstance(ready_body, dict):
        for service in ready_body.get("services", []):
            if service.get("name") == "worker":
                worker = service
    if ready_status != "healthy" or (worker and worker.get("status") != "healthy"):
        print("ASI-7: /health/ready worker is degraded. job_id captured. Do not claim searchable ingest.")
        print("ready_status", ready_status, "worker", json.dumps(_redact(worker)))
        return 0

    print("ASI-7 PASS: remem_query 2xx JSON and remem_ingest job_id via plugin tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
