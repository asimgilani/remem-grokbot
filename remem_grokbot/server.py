from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from remem_grokbot.client import RememClient, RememConfigError
from remem_grokbot.policy import CanonicalUuidError, NamespacePolicy, canonical_uuid

server = Server("remem-grokbot")
MAX_RESPONSE_CHARS = 50_000

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

_NAMESPACES_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Filter results to these namespaces. "
        "When omitted, Grok Bot sends [\"default\", \"grokbot\"]. "
        "Never silently [\"*\"]."
    ),
}

_NAMESPACE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": (
        "Write namespace. Grok Bot coerces writes to grokbot "
        "(or REMEM_DEFAULT_NAMESPACE when it is not default)."
    ),
}


def _default_mode() -> str:
    return "fast"


def _default_max_results() -> int:
    return 10


def _truncate_response(text: str, max_size: int = MAX_RESPONSE_CHARS) -> str:
    if len(text) <= max_size:
        return text
    return text[: max_size - 200] + "\n\n[Response truncated. Narrow your query for more detail.]"


def _format_search_results(data: dict[str, Any]) -> str:
    results = []
    for doc in data.get("results", []):
        title = doc.get("title") or "Untitled"
        for chunk in doc.get("chunks", []):
            try:
                score = float(chunk.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            content = chunk.get("content") or ""
            results.append(f"**{title}** (score: {score:.2f})\n{content}\n")
    if not results:
        return "No results found."
    return "\n---\n".join(results)


def _inject_namespaces_post(payload: dict[str, Any], namespaces: list[str]) -> None:
    payload["namespaces"] = namespaces


def _inject_namespaces_get(params: dict[str, Any], namespaces: list[str]) -> None:
    params["namespaces"] = ",".join(namespaces)


def build_tools() -> list[Tool]:
    return [
        Tool(
            name="remem_query",
            description="Query Remem for relevant context. Returns the raw JSON response from POST /v1/query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "mode": {
                        "type": "string",
                        "description": "Query mode",
                        "enum": ["fast", "rich"],
                        "default": _default_mode(),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max document results (default 10)",
                        "default": _default_max_results(),
                    },
                    "synthesize": {
                        "type": "boolean",
                        "description": "If true, request LLM synthesis (rich mode only)",
                        "default": False,
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional Remem query filters.",
                        "additionalProperties": True,
                    },
                    "include_facts": {
                        "type": "boolean",
                        "description": "Include memory layer facts in results",
                    },
                    "entity": {
                        "type": "string",
                        "description": "Scope facts to a specific entity name",
                    },
                    "facts_only_latest": {
                        "type": "boolean",
                        "description": "Only return latest (non-superseded) facts",
                        "default": True,
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="remem_search",
            description="Search Remem (POST /v1/query mode=fast). Not GET /v1/search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max document results (default 10)",
                        "default": _default_max_results(),
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="remem_summarize",
            description="Rich synthesized answer with sources (POST /v1/query mode=rich, synthesize=true).",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Question to answer"},
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="remem_get_document",
            description="Fetch a document by UUID (GET /v1/documents/{document_id}).",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Document UUID"},
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="remem_get_document_chunks",
            description="Fetch decrypted chunks (GET /v1/documents/{document_id}/chunks).",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Document UUID"},
                    "include_content": {
                        "type": "boolean",
                        "description": "Include decrypted chunk content",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max chunks to return (default 200, max 1000)",
                        "default": 200,
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="remem_memory_query",
            description="Query the knowledge graph (POST /v1/query include_facts=true).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for facts"},
                    "entity": {
                        "type": "string",
                        "description": "Optional entity name to scope results to",
                    },
                    "latest_only": {
                        "type": "boolean",
                        "description": "Only return latest (non-superseded) facts",
                        "default": True,
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="remem_list_entities",
            description="List memory entities (GET /v1/entities).",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Filter by entity type (e.g. person, org, project, technology)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entities to return (default 50, max 200)",
                        "default": 50,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (default 0)",
                        "default": 0,
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
            },
        ),
        Tool(
            name="remem_get_entity_facts",
            description="Get facts for an entity UUID (GET /v1/entities/{entity_id}/facts).",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity UUID"},
                    "latest_only": {
                        "type": "boolean",
                        "description": "Only return latest (non-superseded) facts",
                        "default": True,
                    },
                    "fact_type": {
                        "type": "string",
                        "description": "Filter by fact type: fact, preference, episode, decision",
                    },
                    "namespaces": _NAMESPACES_SCHEMA,
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="remem_extract_facts",
            description="Trigger fact extraction (POST /v1/documents/{document_id}/extract-facts).",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Document UUID"},
                    "namespace": _NAMESPACE_SCHEMA,
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="remem_ingest",
            description="Ingest text (POST /v1/documents/ingest JSON content). Not POST /v1/ingest.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Optional title"},
                    "content": {"type": "string", "description": "Document content"},
                    "metadata": {"type": "object", "description": "Optional metadata object"},
                    "source": {
                        "type": "string",
                        "description": "Ingestion source (default: api)",
                        "default": "api",
                    },
                    "source_id": {"type": "string", "description": "Optional external source id"},
                    "source_path": {"type": "string", "description": "Optional source path/URI"},
                    "mime_type": {"type": "string", "description": "Optional MIME type"},
                    "return_id": {
                        "type": "boolean",
                        "description": "If true, return the document_id immediately",
                        "default": False,
                    },
                    "namespace": _NAMESPACE_SCHEMA,
                },
                "required": ["content"],
            },
        ),
    ]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return build_tools()


async def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    client: RememClient | None = None,
    policy: NamespacePolicy | None = None,
) -> list[TextContent]:
    remem = client or RememClient()
    ns_policy = policy or NamespacePolicy.from_env()
    try:
        if name == "remem_query":
            mode = str(arguments.get("mode") or _default_mode()).strip().lower()
            if mode not in {"fast", "rich"}:
                mode = _default_mode()
            try:
                max_results = int(arguments.get("max_results", _default_max_results()))
            except (TypeError, ValueError):
                max_results = _default_max_results()
            payload: dict[str, Any] = {
                "query": arguments["query"],
                "mode": mode,
                "max_results": max_results,
                "synthesize": bool(arguments.get("synthesize", False)),
            }
            raw_filters = arguments.get("filters")
            if isinstance(raw_filters, dict):
                payload["filters"] = raw_filters
            if "include_facts" in arguments:
                payload["include_facts"] = bool(arguments["include_facts"])
            if arguments.get("entity"):
                payload["entity"] = arguments["entity"]
            if "facts_only_latest" in arguments:
                payload["facts_only_latest"] = bool(arguments["facts_only_latest"])
            _inject_namespaces_post(payload, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.query(payload)
            return [TextContent(type="text", text=_truncate_response(json.dumps(data, indent=2)))]

        if name == "remem_search":
            try:
                limit = int(arguments.get("limit", _default_max_results()))
            except (TypeError, ValueError):
                limit = _default_max_results()
            payload = {
                "query": arguments["query"],
                "mode": "fast",
                "max_results": limit,
            }
            _inject_namespaces_post(payload, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.query(payload)
            return [TextContent(type="text", text=_truncate_response(_format_search_results(data)))]

        if name == "remem_summarize":
            payload = {
                "query": arguments["question"],
                "mode": "rich",
                "max_results": _default_max_results(),
                "synthesize": True,
            }
            _inject_namespaces_post(payload, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.query(payload)
            synthesis = data.get("synthesis")
            if synthesis:
                sources = data.get("sources") or []
                sources_text = "\n".join(str(s) for s in sources) if sources else "(none)"
                text = f"{synthesis}\n\n**Sources:**\n{sources_text}"
                return [TextContent(type="text", text=_truncate_response(text))]
            return [TextContent(type="text", text="No synthesis returned.")]

        if name == "remem_get_document":
            document_id = canonical_uuid(arguments["document_id"], "document_id")
            params: dict[str, Any] = {}
            _inject_namespaces_get(params, ns_policy.resolve_read(arguments.get("namespaces")))
            doc = await remem.request("GET", f"/v1/documents/{document_id}", params=params)
            return [TextContent(type="text", text=_truncate_response(json.dumps(doc, indent=2)))]

        if name == "remem_get_document_chunks":
            document_id = canonical_uuid(arguments["document_id"], "document_id")
            params = {
                "include_content": bool(arguments.get("include_content", True)),
                "limit": int(arguments.get("limit", 200)),
            }
            _inject_namespaces_get(params, ns_policy.resolve_read(arguments.get("namespaces")))
            chunks = await remem.request("GET", f"/v1/documents/{document_id}/chunks", params=params)
            return [TextContent(type="text", text=_truncate_response(json.dumps(chunks, indent=2)))]

        if name == "remem_memory_query":
            payload = {
                "query": arguments["query"],
                "mode": "fast",
                "max_results": 10,
                "include_facts": True,
                "facts_only_latest": bool(arguments.get("latest_only", True)),
            }
            if arguments.get("entity"):
                payload["entity"] = arguments["entity"]
            _inject_namespaces_post(payload, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.query(payload)
            facts = data.get("facts", [])
            if not facts:
                return [TextContent(type="text", text="No facts found.")]
            lines = []
            for fact in facts:
                line = f"- [{fact.get('fact_type', 'fact')}] {fact.get('content', '')}"
                if fact.get("confidence"):
                    line += f" (confidence: {fact['confidence']:.1f})"
                if fact.get("entities"):
                    line += f" | entities: {', '.join(fact['entities'])}"
                lines.append(line)
            return [TextContent(type="text", text=_truncate_response("\n".join(lines)))]

        if name == "remem_list_entities":
            params = {
                "limit": int(arguments.get("limit", 50)),
                "offset": int(arguments.get("offset", 0)),
            }
            if arguments.get("entity_type"):
                params["type"] = arguments["entity_type"]
            _inject_namespaces_get(params, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.request("GET", "/v1/entities", params=params)
            entities = data.get("entities", [])
            if not entities:
                return [TextContent(type="text", text="No entities found.")]
            lines = [f"**Entities** ({data.get('total', len(entities))} total)\n"]
            for entity in entities:
                lines.append(
                    f"- **{entity.get('name', '?')}** ({entity.get('entity_type', '?')}) "
                    f"— {entity.get('fact_count', 0)} facts, {entity.get('mention_count', 0)} mentions "
                    f"[id: {entity.get('id', '?')}]"
                )
            return [TextContent(type="text", text=_truncate_response("\n".join(lines)))]

        if name == "remem_get_entity_facts":
            entity_id = canonical_uuid(arguments["entity_id"], "entity_id")
            params = {"latest_only": bool(arguments.get("latest_only", True))}
            if arguments.get("fact_type"):
                params["fact_type"] = arguments["fact_type"]
            _inject_namespaces_get(params, ns_policy.resolve_read(arguments.get("namespaces")))
            data = await remem.request("GET", f"/v1/entities/{entity_id}/facts", params=params)
            entity = data.get("entity", {})
            facts = data.get("facts", [])
            lines = [f"**{entity.get('name', '?')}** ({entity.get('entity_type', '?')})\n"]
            if not facts:
                lines.append("No facts found.")
            else:
                for fact in facts:
                    line = f"- [{fact.get('fact_type', 'fact')}] {fact.get('content', '')}"
                    if fact.get("confidence"):
                        line += f" (confidence: {fact['confidence']:.1f})"
                    lines.append(line)
                    for rel in fact.get("relationships", []):
                        lines.append(
                            f"  -> {rel.get('rel_type', '?')}: {rel.get('related_fact_content', '')}"
                        )
            return [TextContent(type="text", text=_truncate_response("\n".join(lines)))]

        if name == "remem_extract_facts":
            document_id = canonical_uuid(arguments["document_id"], "document_id")
            params = {"namespace": ns_policy.resolve_write(arguments.get("namespace"))}
            data = await remem.request(
                "POST",
                f"/v1/documents/{document_id}/extract-facts",
                params=params,
            )
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        if name == "remem_ingest":
            source = arguments.get("source")
            if source is None:
                source = "api"
            payload = {
                "title": arguments.get("title"),
                "content": arguments["content"],
                "metadata": arguments.get("metadata") or {},
                "source": source,
                "source_id": arguments.get("source_id"),
                "source_path": arguments.get("source_path"),
                "mime_type": arguments.get("mime_type"),
                "return_id": bool(arguments.get("return_id", False)),
                "namespace": ns_policy.resolve_write(arguments.get("namespace")),
            }
            result = await remem.ingest(payload)
            return [TextContent(type="text", text=_truncate_response(json.dumps(result, indent=2)))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except CanonicalUuidError as exc:
        return [TextContent(type="text", text=str(exc))]
    except RememConfigError as exc:
        return [TextContent(type="text", text=_truncate_response(f"Error: {exc}"))]
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        msg = f"HTTP {exc.response.status_code} calling Remem API: {body}"
        return [TextContent(type="text", text=_truncate_response(msg))]
    except Exception as exc:
        return [TextContent(type="text", text=_truncate_response(f"Error: {exc}"))]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    return await dispatch_tool(name, arguments)


async def _main_async() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
