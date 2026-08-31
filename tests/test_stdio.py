from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StdioSpawnTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_python3_spawn_lists_ten_tools(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        params = StdioServerParameters(
            command="python3",
            args=[str(ROOT / "server.py")],
            env=env,
            cwd=str(ROOT),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
        names = [tool.name for tool in listed.tools]
        self.assertEqual(
            names,
            [
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
            ],
        )
        summarize = next(tool for tool in listed.tools if tool.name == "remem_summarize")
        schema = summarize.inputSchema
        self.assertIn("question", schema["required"])


if __name__ == "__main__":
    unittest.main()
