#!/usr/bin/env python3
"""Contract tests for the remem-grokbot connector. No live key required."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import unittest
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


HOUSE = [
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
]


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RecordingOpener:
    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout=None):
        body = request.data.decode("utf-8") if request.data else ""
        parsed = json.loads(body) if body else None
        self.calls.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "headers": {k.lower(): v for k, v in request.header_items()},
                "json": parsed,
            }
        )
        path = request.full_url.split("?", 1)[0]
        if path.endswith("/health"):
            return FakeHTTPResponse({"status": "healthy", "version": "0.1.0"})
        if path.endswith("/v1/query"):
            return FakeHTTPResponse(
                {
                    "mode": (parsed or {}).get("mode", "fast"),
                    "query": (parsed or {}).get("query"),
                    "results": [],
                    "total_chunks": 0,
                    "latency_ms": 1,
                    "namespaces": (parsed or {}).get("namespaces"),
                }
            )
        if path.endswith("/ingest"):
            return FakeHTTPResponse({"job_id": "job-1", "message": "queued", "document_id": "doc-1"})
        if path.endswith("/extract-facts"):
            return FakeHTTPResponse(
                {"status": "accepted", "document_id": "doc-1", "fact_extraction_status": "queued"},
                status=202,
            )
        if path.endswith("/chunks"):
            return FakeHTTPResponse({"document_id": "doc-1", "chunks": []})
        if "/documents/" in path:
            return FakeHTTPResponse({"document_id": "doc-1", "content": "hello", "source": "api"})
        if path.endswith("/entities"):
            return FakeHTTPResponse({"entities": [], "total": 0, "limit": 50, "offset": 0})
        if path.endswith("/facts"):
            return FakeHTTPResponse({"entity": {"id": "e1", "name": "x"}, "facts": [], "total": 0})
        return FakeHTTPResponse({"ok": True})


def client_with(opener, **overrides):
    config = server.load_config(
        {
            "REMEM_API_KEY": "vlt_test_key_not_real",
            "REMEM_API_URL": "https://api.remem.io",
            "REMEM_DEFAULT_NAMESPACE": "grokbot",
            **overrides,
        }
    )
    return server.RememClient(config, opener=opener)


class ManifestTests(unittest.TestCase):
    def test_plugin_manifest(self):
        plugin = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["name"], "remem-grokbot")
        self.assertRegex(plugin["name"], r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
        self.assertEqual(plugin["mcpServers"], "./mcp.json")
        self.assertIn("REMEM_API_KEY", plugin["variables"]["required"])
        self.assertEqual(
            plugin["variables"]["properties"]["REMEM_API_URL"]["default"],
            "https://api.remem.io",
        )
        self.assertEqual(
            plugin["variables"]["properties"]["REMEM_DEFAULT_NAMESPACE"]["default"],
            "grokbot",
        )

    def test_mcp_stdio_uses_system_python3(self):
        mcp = json.loads((ROOT / "mcp.json").read_text())
        remem = mcp["mcpServers"]["remem"]
        self.assertEqual(remem["command"], "python3")
        self.assertNotIn(".venv", remem["command"])
        self.assertTrue(any("server.py" in str(arg) for arg in remem["args"]))
        joined = " ".join([remem["command"], *remem["args"]])
        self.assertNotIn(".venv/bin/python", joined)
        self.assertEqual(remem["env"]["REMEM_API_URL"], "${REMEM_API_URL}")
        self.assertNotIn("https://mcp.remem.io", json.dumps(mcp))

    def test_connector_never_posts_wrong_ingest_path(self):
        source = (ROOT / "server.py").read_text()
        self.assertIn('"/v1/documents/ingest"', source)
        self.assertIn("Refusing POST /v1/ingest", source)
        self.assertNotIn("https://mcp.remem.io", source)
        self.assertNotIn(".venv/bin/python", source)
        self.assertNotIn("mem_store", server.HANDLERS)
        self.assertNotIn("mem_recall", server.HANDLERS)

    def test_poteto_mode_vendored(self):
        skill = ROOT / ".cursor" / "skills" / "poteto-mode" / "SKILL.md"
        self.assertTrue(skill.is_file(), "poteto-mode skill must be in checkout")
        body = skill.read_text()
        self.assertIn("Poteto Mode", body)
        self.assertIn("/poteto-mode", body)

    def test_skill_exists(self):
        skill = ROOT / "skills" / "remem-memory" / "SKILL.md"
        self.assertTrue(skill.is_file())
        body = skill.read_text()
        self.assertIn("grokbot", body)
        self.assertIn("default", body)
        self.assertIn("53852812", body)
        self.assertNotIn("Claude marketplace", body)


class NamespaceAndHttpTests(unittest.TestCase):
    def test_ten_house_tools_only(self):
        names = [tool["name"] for tool in server.tool_definitions()]
        self.assertEqual(names, HOUSE)
        self.assertNotIn("mem_store", names)
        self.assertNotIn("mem_recall", names)

    def test_omitted_read_namespaces(self):
        self.assertEqual(server.read_namespaces(None), ["default", "grokbot"])

    def test_explicit_read_namespaces_preserved(self):
        self.assertEqual(server.read_namespaces(["work"]), ["work"])

    def test_write_never_default(self):
        cfg = server.load_config(
            {
                "REMEM_API_KEY": "vlt_x",
                "REMEM_DEFAULT_NAMESPACE": "default",
            }
        )
        self.assertEqual(cfg["write_namespace"], "grokbot")
        self.assertEqual(server.write_namespace(cfg, "default"), "grokbot")
        self.assertEqual(server.write_namespace(cfg, None), "grokbot")
        self.assertEqual(server.write_namespace(cfg, "work"), "grokbot")

    def test_query_posts_v1_query_with_default_namespaces(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(client, "remem_query", {"query": "hello"})
        query_calls = [c for c in opener.calls if c["url"].endswith("/v1/query")]
        self.assertEqual(len(query_calls), 1)
        self.assertEqual(query_calls[0]["method"], "POST")
        self.assertEqual(query_calls[0]["json"]["namespaces"], ["default", "grokbot"])
        self.assertTrue(any(c["url"].endswith("/health") for c in opener.calls))

    def test_search_is_post_query_fast_not_get_search(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(client, "remem_search", {"query": "hello"})
        urls = [c["url"] for c in opener.calls]
        self.assertTrue(any(u.endswith("/v1/query") for u in urls))
        self.assertFalse(any("/v1/search" in u for u in urls))
        body = next(c["json"] for c in opener.calls if c["url"].endswith("/v1/query"))
        self.assertEqual(body["mode"], "fast")

    def test_summarize_rich_synthesize(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(client, "remem_summarize", {"query": "hello"})
        body = next(c["json"] for c in opener.calls if c["url"].endswith("/v1/query"))
        self.assertEqual(body["mode"], "rich")
        self.assertTrue(body["synthesize"])

    def test_memory_query_include_facts(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(client, "remem_memory_query", {"query": "stack", "entity": "Acme"})
        body = next(c["json"] for c in opener.calls if c["url"].endswith("/v1/query"))
        self.assertTrue(body["include_facts"])
        self.assertEqual(body["entity"], "Acme")
        self.assertEqual(body["namespaces"], ["default", "grokbot"])

    def test_ingest_json_path_namespace_and_idempotency(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(
            client,
            "remem_ingest",
            {"content": "note from grokbot", "namespace": "default", "return_id": True},
        )
        ingest = next(c for c in opener.calls if c["url"].endswith("/v1/documents/ingest"))
        self.assertEqual(ingest["method"], "POST")
        self.assertEqual(ingest["json"]["content"], "note from grokbot")
        self.assertEqual(ingest["json"]["namespace"], "grokbot")
        self.assertNotEqual(ingest["json"]["namespace"], "default")
        self.assertIn("idempotency-key", ingest["headers"])
        self.assertTrue(ingest["headers"]["idempotency-key"])
        self.assertFalse(any(c["url"].rstrip("/").endswith("/v1/ingest") for c in opener.calls))
        self.assertIn("x-api-key", ingest["headers"])
        self.assertTrue(ingest["headers"]["authorization"].startswith("Bearer "))

    def test_extract_facts_namespace_query_param(self):
        opener = RecordingOpener()
        client = client_with(opener)
        server.dispatch(client, "remem_extract_facts", {"document_id": "doc-1", "namespace": "default"})
        call = next(c for c in opener.calls if "extract-facts" in c["url"])
        self.assertIn("namespace=grokbot", call["url"])
        self.assertNotIn("namespace=default", call["url"])

    def test_missing_key_fails_loud(self):
        opener = RecordingOpener()
        client = client_with(opener, REMEM_API_KEY="")
        with self.assertRaises(server.RememError) as ctx:
            server.dispatch(client, "remem_query", {"query": "hello"})
        self.assertIn("REMEM_API_KEY", str(ctx.exception))

    def test_health_down_fails_loud(self):
        def boom(request, timeout=None):
            raise urllib.error.URLError("simulated outage")

        client = client_with(boom)
        with self.assertRaises(server.RememError) as ctx:
            server.dispatch(client, "remem_query", {"query": "hello"})
        self.assertIn("down", str(ctx.exception).lower())

    def test_refuses_v1_ingest_path(self):
        client = client_with(RecordingOpener())
        with self.assertRaises(server.RememError):
            client.request("POST", "/v1/ingest", json_body={"content": "nope"})

    def test_redact_never_prints_key(self):
        key = "vlt_super_secret_value"
        self.assertNotIn(key, server.redact(f"header {key} leaked", key))

    def test_mcp_tools_list_roundtrip(self):
        opener = RecordingOpener()
        client = client_with(opener)
        reply = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, client)
        names = [t["name"] for t in reply["result"]["tools"]]
        self.assertEqual(names, HOUSE)

    def test_stdio_python3_spawn_not_venv(self):
        which = subprocess.check_output(["which", "python3"], text=True).strip()
        self.assertEqual(which, "/usr/bin/python3")
        self.assertFalse((ROOT / ".venv" / "bin" / "python").exists())
        init = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
            }
        ).encode()
        framed = f"Content-Length: {len(init)}\r\n\r\n".encode() + init
        proc = subprocess.run(
            ["python3", str(ROOT / "server.py")],
            input=framed,
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertIn(b"remem-grokbot", proc.stdout)
        self.assertNotIn(b".venv/bin/python", proc.stderr)


class LiveAcceptanceTests(unittest.TestCase):
    @unittest.skipUnless(
        bool(os.environ.get("REMEM_API_KEY") and not os.environ.get("REMEM_API_KEY", "").startswith("${")),
        "REMEM_API_KEY missing in this cloud environment. Live remem_query/remem_ingest NOT run. "
        "Do not treat contract tests as a live ingest pass.",
    )
    def test_live_query_and_ingest(self):
        client = server.RememClient(server.load_config())
        health = client.health()
        self.assertIn(health.get("status"), ("healthy", "ok", None))
        ingested = server.dispatch(
            client,
            "remem_ingest",
            {
                "content": "remem-grokbot live acceptance probe. Writes must land in grokbot.",
                "title": "remem-grokbot acceptance",
                "return_id": True,
                "source": "api",
            },
        )
        self.assertTrue(ingested.get("job_id") or ingested.get("document_id"))
        queried = server.dispatch(client, "remem_query", {"query": "remem-grokbot acceptance"})
        self.assertIn("results", queried)


if __name__ == "__main__":
    unittest.main()
