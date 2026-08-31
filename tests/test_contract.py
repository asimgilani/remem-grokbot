from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from remem_grokbot.client import INGEST_PATH, QUERY_PATH, RememClient
from remem_grokbot.policy import (
    CanonicalUuidError,
    NamespacePolicy,
    canonical_uuid,
)
from remem_grokbot.server import TOOL_NAMES, build_tools, dispatch_tool

ROOT = Path(__file__).resolve().parents[1]


class ToolShapeTests(unittest.TestCase):
    def test_list_tools_ten_names(self) -> None:
        tools = build_tools()
        names = [tool.name for tool in tools]
        self.assertEqual(tuple(names), TOOL_NAMES)
        self.assertEqual(len(names), 10)
        self.assertEqual(len(set(names)), 10)

    def test_summarize_required_question(self) -> None:
        summarize = next(tool for tool in build_tools() if tool.name == "remem_summarize")
        schema = summarize.inputSchema
        self.assertIn("question", schema["properties"])
        self.assertIn("question", schema["required"])
        self.assertNotIn("query", schema.get("required", []))


class NamespacePolicyTests(unittest.TestCase):
    def test_omitted_read_namespaces(self) -> None:
        policy = NamespacePolicy.from_env({})
        self.assertEqual(policy.resolve_read(None), ["default", "grokbot"])
        self.assertEqual(policy.resolve_read([]), ["default", "grokbot"])

    def test_explicit_read_namespaces_kept(self) -> None:
        policy = NamespacePolicy.from_env({})
        self.assertEqual(policy.resolve_read(["work"]), ["work"])

    def test_write_without_namespace_is_grokbot(self) -> None:
        policy = NamespacePolicy.from_env({})
        self.assertEqual(policy.resolve_write(None), "grokbot")

    def test_write_default_coerced_to_grokbot(self) -> None:
        policy = NamespacePolicy.from_env({"REMEM_DEFAULT_NAMESPACE": "default"})
        self.assertEqual(policy.resolve_write("default"), "grokbot")

    def test_honor_non_default_env_namespace(self) -> None:
        policy = NamespacePolicy.from_env({"REMEM_DEFAULT_NAMESPACE": "research"})
        self.assertEqual(policy.resolve_write(None), "research")

    def test_never_silently_star(self) -> None:
        policy = NamespacePolicy.from_env({})
        self.assertNotEqual(policy.resolve_read(None), ["*"])


class CanonicalUuidTests(unittest.TestCase):
    def test_canonical_uuid(self) -> None:
        raw = "3F2F0000-0000-4000-8000-000000000001"
        self.assertEqual(canonical_uuid(raw, "document_id"), raw.lower())

    def test_rejects_non_uuid(self) -> None:
        with self.assertRaises(CanonicalUuidError):
            canonical_uuid("not-a-uuid", "document_id")


class IngestPathTests(unittest.TestCase):
    def test_ingest_constant(self) -> None:
        self.assertEqual(INGEST_PATH, "/v1/documents/ingest")
        self.assertEqual(QUERY_PATH, "/v1/query")

    def test_tree_forbids_post_v1_ingest(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "POST /v1/ingest" in text:
                for line in text.splitlines():
                    if "POST /v1/ingest" not in line:
                        continue
                    lowered = line.lower()
                    if any(word in lowered for word in ("not ", "never", "forbidden", "forbids")):
                        continue
                    offenders.append(f"{path}:{line.strip()}")
        self.assertEqual(offenders, [])


class SpawnTests(unittest.TestCase):
    def test_mcp_json_python3_not_venv(self) -> None:
        data = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
        remem = data["mcpServers"]["remem"]
        self.assertEqual(remem["command"], "python3")
        joined = " ".join([remem["command"], *remem["args"]])
        self.assertNotIn(".venv", joined)
        self.assertNotIn(".venv/bin/python", joined)

    def test_no_venv_spawn_in_tree(self) -> None:
        for path in (ROOT / "mcp.json", ROOT / "README.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(".venv/bin/python", text.replace("Never `.venv/bin/python`", ""))


class PinsTests(unittest.TestCase):
    def test_pyproject_pins(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("mcp==1.26.0", text)
        self.assertIn("httpx==0.28.1", text)


class ManifestTests(unittest.TestCase):
    def test_plugin_name_kebab(self) -> None:
        data = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "remem-grokbot")
        self.assertIn("REMEM_API_KEY", data["variables"]["properties"])
        self.assertTrue(data["variables"]["properties"]["REMEM_API_KEY"]["secret"])

    def test_no_poteto_mode_in_tree(self) -> None:
        banned = ROOT / ".cursor" / "skills" / "poteto-mode"
        self.assertFalse(banned.exists())

    def test_skill_exists(self) -> None:
        skill = ROOT / "skills" / "remem-memory" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("Write only to `grokbot`", text)
        self.assertIn("macOS Claude plugin", text)


class ClientHeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_sends_dual_auth_and_idempotency(self) -> None:
        captured: dict[str, object] = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def request(self, method, url, headers=None, json=None, params=None):
                captured["method"] = method
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json

                class Resp:
                    def raise_for_status(self) -> None:
                        return None

                    def json(self):
                        return {"job_id": "test-job", "message": "queued"}

                return Resp()

        import remem_grokbot.client as client_mod

        original = client_mod.httpx.AsyncClient
        client_mod.httpx.AsyncClient = FakeAsyncClient  # type: ignore[assignment]
        try:
            client = RememClient(api_url="https://api.remem.io", api_key="vlt_test")
            result = await client.ingest(
                {"content": "hello", "namespace": "grokbot", "return_id": True}
            )
        finally:
            client_mod.httpx.AsyncClient = original  # type: ignore[assignment]

        self.assertEqual(result["job_id"], "test-job")
        self.assertTrue(str(captured["url"]).endswith("/v1/documents/ingest"))
        headers = captured["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers["Authorization"], "Bearer vlt_test")
        self.assertEqual(headers["X-API-Key"], "vlt_test")
        self.assertIn("Idempotency-Key", headers)
        body = captured["json"]
        assert isinstance(body, dict)
        self.assertEqual(body["namespace"], "grokbot")
        self.assertEqual(body["content"], "hello")


class DispatchNamespaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_omitted_namespaces(self) -> None:
        remem = RememClient(api_url="https://api.remem.io", api_key="vlt_test")
        remem.query = AsyncMock(return_value={"mode": "fast", "query": "hi", "results": [], "total_chunks": 0, "latency_ms": 1})  # type: ignore[method-assign]
        await dispatch_tool(
            "remem_query",
            {"query": "hi"},
            client=remem,
            policy=NamespacePolicy.from_env({}),
        )
        payload = remem.query.await_args.args[0]
        self.assertEqual(payload["namespaces"], ["default", "grokbot"])

    async def test_ingest_omitted_namespace_writes_grokbot(self) -> None:
        remem = RememClient(api_url="https://api.remem.io", api_key="vlt_test")
        remem.ingest = AsyncMock(return_value={"job_id": "j1", "message": "queued"})  # type: ignore[method-assign]
        await dispatch_tool(
            "remem_ingest",
            {"content": "note", "return_id": True},
            client=remem,
            policy=NamespacePolicy.from_env({}),
        )
        payload = remem.ingest.await_args.args[0]
        self.assertEqual(payload["namespace"], "grokbot")
        self.assertTrue(payload["return_id"])

    async def test_get_document_namespaces_comma_separated(self) -> None:
        remem = RememClient(api_url="https://api.remem.io", api_key="vlt_test")
        remem.request = AsyncMock(return_value={"id": "x"})  # type: ignore[method-assign]
        doc_id = "11111111-1111-4111-8111-111111111111"
        await dispatch_tool(
            "remem_get_document",
            {"document_id": doc_id},
            client=remem,
            policy=NamespacePolicy.from_env({}),
        )
        kwargs = remem.request.await_args.kwargs
        self.assertEqual(kwargs["params"]["namespaces"], "default,grokbot")


class SourceGuardTests(unittest.TestCase):
    def test_server_reads_remem_api_key_env(self) -> None:
        client_src = (ROOT / "remem_grokbot" / "client.py").read_text(encoding="utf-8")
        self.assertIn("REMEM_API_KEY", client_src)
        self.assertNotIn("REMEM_API_KEY_FD", client_src)
        tree = ast.parse(client_src)
        self.assertTrue(tree.body)


if __name__ == "__main__":
    unittest.main()
