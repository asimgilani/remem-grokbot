#!/usr/bin/env python3
"""Remem MCP stdio server for Grok Bot / Cursor.

Talks HTTP to https://api.remem.io. Uses system python3. No venv spawn.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_API_URL = "https://api.remem.io"
FORCED_WRITE_NAMESPACE = "grokbot"
DEFAULT_READ_NAMESPACES = ["default", "grokbot"]
HOUSE_TOOLS = (
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


class RememError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _strip_placeholder(name: str, raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value in {f"${{{name}}}", f"${name}"}:
        return None
    return value


def load_config(env: dict[str, str] | None = None) -> dict[str, str]:
    source = env if env is not None else os.environ
    api_url = _strip_placeholder("REMEM_API_URL", source.get("REMEM_API_URL")) or DEFAULT_API_URL
    api_url = api_url.rstrip("/")
    api_key = _strip_placeholder("REMEM_API_KEY", source.get("REMEM_API_KEY"))
    write_ns = _strip_placeholder(
        "REMEM_DEFAULT_NAMESPACE", source.get("REMEM_DEFAULT_NAMESPACE")
    ) or FORCED_WRITE_NAMESPACE
    if write_ns == "default":
        write_ns = FORCED_WRITE_NAMESPACE
    return {
        "api_url": api_url,
        "api_key": api_key or "",
        "write_namespace": write_ns,
    }


def write_namespace(config: dict[str, str], requested: str | None) -> str:
    del requested
    ns = config.get("write_namespace") or FORCED_WRITE_NAMESPACE
    if ns == "default":
        return FORCED_WRITE_NAMESPACE
    return ns


def read_namespaces(requested: Any) -> list[str]:
    if requested is None:
        return list(DEFAULT_READ_NAMESPACES)
    if isinstance(requested, str):
        parts = [part.strip() for part in requested.split(",") if part.strip()]
        return parts or list(DEFAULT_READ_NAMESPACES)
    if isinstance(requested, (list, tuple)):
        parts = [str(part).strip() for part in requested if str(part).strip()]
        return parts or list(DEFAULT_READ_NAMESPACES)
    raise RememError("namespaces must be a list of namespace keys")


def require_api_key(config: dict[str, str]) -> str:
    key = config.get("api_key") or ""
    if not key:
        raise RememError(
            "REMEM_API_KEY is missing. Set the plugin setup secret REMEM_API_KEY "
            "(vlt_...). Refusing to call Remem."
        )
    return key


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "remem-grokbot/1.0",
    }


def redact(text: str, api_key: str) -> str:
    if api_key and api_key in text:
        return text.replace(api_key, "vlt_[redacted]")
    return text


class RememClient:
    def __init__(self, config: dict[str, str], opener: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._opener = opener or urllib.request.urlopen

    def health(self) -> dict[str, Any]:
        url = f"{self.config['api_url']}/health"
        request = urllib.request.Request(url, method="GET")
        try:
            with self._opener(request, timeout=10) as response:
                body = response.read().decode("utf-8")
                status = getattr(response, "status", 200)
                payload = _decode_json(body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RememError(
                f"Remem health check failed: HTTP {exc.code} at {url}. {detail[:300]}",
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise RememError(
                f"Remem is down or unreachable at {url}: {exc.reason}. Fail loud. Do not invent paths."
            ) from exc
        if status != 200 or (isinstance(payload, dict) and payload.get("status") not in (None, "healthy", "ok")):
            raise RememError(f"Remem /health is not healthy: HTTP {status} {payload!r}")
        return payload if isinstance(payload, dict) else {"status": "healthy", "raw": payload}

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> Any:
        if path == "/v1/ingest" or path.startswith("/v1/ingest"):
            raise RememError("Refusing POST /v1/ingest. Use POST /v1/documents/ingest.")
        self.health()
        api_key = require_api_key(self.config)
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.config['api_url']}{path}"
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None},
                doseq=True,
            )
            if encoded:
                url = f"{url}?{encoded}"
        data = None
        req_headers = auth_headers(api_key)
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with self._opener(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", errors="replace"), api_key)
            raise RememError(
                f"Remem {method} {path} failed: HTTP {exc.code}. {detail[:800]}",
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise RememError(
                f"Remem is down or unreachable for {method} {path}: {exc.reason}."
            ) from exc
        if not raw:
            return {"ok": True, "status": status}
        return _decode_json(raw)


def _decode_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RememError(f"Remem returned non-JSON: {raw[:300]}") from exc


def _require(args: dict[str, Any], key: str) -> Any:
    if key not in args or args[key] in (None, ""):
        raise RememError(f"Missing required argument: {key}")
    return args[key]


def handle_query(client: RememClient, args: dict[str, Any], *, overrides: dict[str, Any] | None = None) -> Any:
    payload = {
        "query": _require(args, "query"),
    }
    optional = (
        "mode",
        "max_results",
        "synthesize",
        "filters",
        "include_facts",
        "entity",
        "facts_only_latest",
    )
    for key in optional:
        if key in args and args[key] is not None:
            payload[key] = args[key]
    if "latest_only" in args and args["latest_only"] is not None and "facts_only_latest" not in payload:
        payload["facts_only_latest"] = args["latest_only"]
    payload["namespaces"] = read_namespaces(args.get("namespaces"))
    if overrides:
        payload.update(overrides)
        if "namespaces" not in overrides:
            payload["namespaces"] = read_namespaces(args.get("namespaces"))
    return client.request("POST", "/v1/query", json_body=payload)


def handle_search(client: RememClient, args: dict[str, Any]) -> Any:
    return handle_query(
        client,
        args,
        overrides={"mode": "fast"},
    )


def handle_summarize(client: RememClient, args: dict[str, Any]) -> Any:
    return handle_query(
        client,
        args,
        overrides={"mode": "rich", "synthesize": True},
    )


def handle_memory_query(client: RememClient, args: dict[str, Any]) -> Any:
    return handle_query(
        client,
        args,
        overrides={"include_facts": True},
    )


def handle_get_document(client: RememClient, args: dict[str, Any]) -> Any:
    document_id = urllib.parse.quote(_require(args, "document_id"), safe="")
    return client.request("GET", f"/v1/documents/{document_id}")


def handle_get_document_chunks(client: RememClient, args: dict[str, Any]) -> Any:
    document_id = urllib.parse.quote(_require(args, "document_id"), safe="")
    query = {
        "include_content": args.get("include_content"),
        "limit": args.get("limit"),
    }
    return client.request("GET", f"/v1/documents/{document_id}/chunks", query=query)


def handle_list_entities(client: RememClient, args: dict[str, Any]) -> Any:
    entity_type = args.get("type")
    if entity_type is None:
        entity_type = args.get("entity_type")
    query = {
        "type": entity_type,
        "limit": args.get("limit"),
        "offset": args.get("offset"),
    }
    return client.request("GET", "/v1/entities", query=query)


def handle_get_entity_facts(client: RememClient, args: dict[str, Any]) -> Any:
    entity_id = urllib.parse.quote(_require(args, "entity_id"), safe="")
    query = {
        "latest_only": args.get("latest_only"),
        "fact_type": args.get("fact_type"),
    }
    return client.request("GET", f"/v1/entities/{entity_id}/facts", query=query)


def handle_extract_facts(client: RememClient, args: dict[str, Any]) -> Any:
    document_id = urllib.parse.quote(_require(args, "document_id"), safe="")
    namespace = write_namespace(client.config, args.get("namespace"))
    return client.request(
        "POST",
        f"/v1/documents/{document_id}/extract-facts",
        query={"namespace": namespace},
        json_body={},
    )


def handle_ingest(client: RememClient, args: dict[str, Any]) -> Any:
    content = _require(args, "content")
    body: dict[str, Any] = {
        "content": content,
        "namespace": write_namespace(client.config, args.get("namespace")),
    }
    for key in ("title", "source", "source_id", "source_path", "mime_type", "metadata", "return_id"):
        if key in args and args[key] is not None:
            body[key] = args[key]
    idempotency = args.get("idempotency_key") or args.get("Idempotency-Key") or str(uuid.uuid4())
    return client.request(
        "POST",
        "/v1/documents/ingest",
        json_body=body,
        headers={"Idempotency-Key": str(idempotency)},
    )


HANDLERS: dict[str, Callable[[RememClient, dict[str, Any]], Any]] = {
    "remem_query": handle_query,
    "remem_search": handle_search,
    "remem_summarize": handle_summarize,
    "remem_get_document": handle_get_document,
    "remem_get_document_chunks": handle_get_document_chunks,
    "remem_memory_query": handle_memory_query,
    "remem_list_entities": handle_list_entities,
    "remem_get_entity_facts": handle_get_entity_facts,
    "remem_extract_facts": handle_extract_facts,
    "remem_ingest": handle_ingest,
}

QUERY_SCHEMA_PROPS = {
    "query": {"type": "string", "description": "Natural language query (required)."},
    "mode": {"type": "string", "enum": ["fast", "rich"], "description": "Query mode."},
    "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
    "synthesize": {"type": "boolean"},
    "filters": {"type": "object", "additionalProperties": True},
    "include_facts": {"type": "boolean"},
    "entity": {"type": "string"},
    "facts_only_latest": {"type": "boolean"},
    "namespaces": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Namespace keys. Omitted reads become [default, grokbot]. Never silently [*].",
    },
}


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "remem_query",
            "description": "POST /v1/query. Raw Remem query. Reads default to namespaces [default, grokbot].",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": dict(QUERY_SCHEMA_PROPS),
            },
        },
        {
            "name": "remem_search",
            "description": "POST /v1/query with mode=fast. Do not use GET /v1/search.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": QUERY_SCHEMA_PROPS["query"],
                    "max_results": QUERY_SCHEMA_PROPS["max_results"],
                    "namespaces": QUERY_SCHEMA_PROPS["namespaces"],
                    "filters": QUERY_SCHEMA_PROPS["filters"],
                },
            },
        },
        {
            "name": "remem_summarize",
            "description": "POST /v1/query with mode=rich and synthesize=true.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": QUERY_SCHEMA_PROPS["query"],
                    "max_results": QUERY_SCHEMA_PROPS["max_results"],
                    "namespaces": QUERY_SCHEMA_PROPS["namespaces"],
                    "filters": QUERY_SCHEMA_PROPS["filters"],
                },
            },
        },
        {
            "name": "remem_get_document",
            "description": "GET /v1/documents/{document_id}.",
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "string"}},
            },
        },
        {
            "name": "remem_get_document_chunks",
            "description": "GET /v1/documents/{document_id}/chunks.",
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {
                    "document_id": {"type": "string"},
                    "include_content": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            },
        },
        {
            "name": "remem_memory_query",
            "description": "POST /v1/query with include_facts=true.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": QUERY_SCHEMA_PROPS["query"],
                    "entity": QUERY_SCHEMA_PROPS["entity"],
                    "facts_only_latest": QUERY_SCHEMA_PROPS["facts_only_latest"],
                    "latest_only": {"type": "boolean"},
                    "max_results": QUERY_SCHEMA_PROPS["max_results"],
                    "namespaces": QUERY_SCHEMA_PROPS["namespaces"],
                    "filters": QUERY_SCHEMA_PROPS["filters"],
                },
            },
        },
        {
            "name": "remem_list_entities",
            "description": "GET /v1/entities.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Entity type filter."},
                    "entity_type": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "offset": {"type": "integer", "minimum": 0},
                },
            },
        },
        {
            "name": "remem_get_entity_facts",
            "description": "GET /v1/entities/{entity_id}/facts.",
            "inputSchema": {
                "type": "object",
                "required": ["entity_id"],
                "properties": {
                    "entity_id": {"type": "string"},
                    "latest_only": {"type": "boolean"},
                    "fact_type": {"type": "string"},
                },
            },
        },
        {
            "name": "remem_extract_facts",
            "description": "POST /v1/documents/{document_id}/extract-facts. Write. Namespace query param forced to grokbot.",
            "inputSchema": {
                "type": "object",
                "required": ["document_id"],
                "properties": {
                    "document_id": {"type": "string"},
                    "namespace": {
                        "type": "string",
                        "description": "Ignored if default. Connector forces grokbot.",
                    },
                },
            },
        },
        {
            "name": "remem_ingest",
            "description": "POST /v1/documents/ingest JSON. content required. Namespace forced to grokbot. Sends Idempotency-Key.",
            "inputSchema": {
                "type": "object",
                "required": ["content"],
                "properties": {
                    "content": {"type": "string"},
                    "title": {"type": "string"},
                    "source": {"type": "string"},
                    "namespace": {"type": "string"},
                    "source_id": {"type": "string"},
                    "source_path": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "metadata": {"type": "object", "additionalProperties": True},
                    "return_id": {"type": "boolean"},
                    "idempotency_key": {"type": "string"},
                },
            },
        },
    ]


def dispatch(client: RememClient, name: str, args: dict[str, Any] | None) -> Any:
    if name not in HANDLERS:
        raise RememError(
            f"Unknown tool {name!r}. House tools are: {', '.join(HOUSE_TOOLS)}. "
            "mem_store/mem_recall are not provided."
        )
    return HANDLERS[name](client, args or {})


def call_tool(name: str, args: dict[str, Any] | None, client: RememClient | None = None) -> dict[str, Any]:
    active = client or RememClient(load_config())
    try:
        result = dispatch(active, name, args)
        text = json.dumps(result, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except RememError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"Internal connector error: {exc}"}],
            "isError": True,
        }


def _read_message(stdin) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stdin.readline()
        if line == "":
            return None
        if line in ("\r\n", "\n"):
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length_raw = headers.get("content-length")
    if not length_raw:
        return None
    raw = stdin.read(int(length_raw))
    if not raw:
        return None
    return json.loads(raw)


def _write_message(stdout, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n")
    stdout.write(encoded.decode("utf-8"))
    stdout.flush()


def handle_rpc(message: dict[str, Any], client: RememClient) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    if method is None:
        return None
    if method == "initialize":
        requested = params.get("protocolVersion") or PROTOCOL_VERSIONS[0]
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[-1]
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "remem-grokbot", "version": "1.0.0"},
                "instructions": (
                    "Remem Grok Bot connector. Writes always use namespace grokbot. "
                    "Reads omit-namespaces become [default, grokbot]. "
                    "Fail loud if Remem is down. Do not install catalog remem-memory 53852812."
                ),
            },
        }
    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tool_definitions()},
        }
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        result = call_tool(name, args, client=client)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}
    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    stdin = sys.stdin
    stdout = sys.stdout
    client = RememClient(load_config())
    while True:
        try:
            message = _read_message(stdin)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 1
        if message is None:
            return 0
        try:
            reply = handle_rpc(message, client)
        except Exception as exc:
            reply = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": str(exc)},
            }
        if reply is not None:
            _write_message(stdout, reply)


if __name__ == "__main__":
    raise SystemExit(main())
